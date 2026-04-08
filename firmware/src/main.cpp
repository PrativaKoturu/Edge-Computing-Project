#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#ifndef NODE_ID
#define NODE_ID "zone-a"
#endif

#ifndef MQTT_HOST
#define MQTT_HOST "host.wokwi.internal"
#endif

#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif

static const char *WIFI_SSID = "Wokwi-GUEST";
static const char *WIFI_PASS = "";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// Topics
static String topicTelemetry() { return String("edge/") + NODE_ID + "/telemetry"; }
static String topicRequest() { return String("edge/") + NODE_ID + "/request"; }
static String topicPolicy() { return String("edge/") + NODE_ID + "/policy"; }

// Cache (simulated MicroSD index)
static const int CACHE_CAPACITY = 64;
static String cacheKeys[CACHE_CAPACITY];
static uint32_t cacheLastUse[CACHE_CAPACITY];
static int cacheCount = 0;

static int8_t policyWeightsInt8[8] = {0};
static float policyWeightsFloat[8] = {0};
static bool hasPolicy = false;

// Rolling stats for state features
static bool rollingHits[10] = {false};
static int rollingHitPos = 0;
static int rollingHitCount = 0;

static String rollingReq[20];
static int rollingReqPos = 0;
static int rollingReqCount = 0;

static bool rollingEvictions[10] = {false};
static int rollingEvictPos = 0;
static int rollingEvictCount = 0;

static uint32_t lastRequestMs = 0;

static uint32_t nowMs() { return (uint32_t)millis(); }

static int findCacheIdx(const String &key) {
  for (int i = 0; i < cacheCount; i++) {
    if (cacheKeys[i] == key) return i;
  }
  return -1;
}

static void touchCache(int idx) { cacheLastUse[idx] = nowMs(); }

static void insertCache(const String &key) {
  int idx = findCacheIdx(key);
  if (idx >= 0) {
    touchCache(idx);
    return;
  }

  if (cacheCount < CACHE_CAPACITY) {
    cacheKeys[cacheCount] = key;
    cacheLastUse[cacheCount] = nowMs();
    cacheCount++;
    return;
  }

  // Evict LRU
  int lru = 0;
  for (int i = 1; i < CACHE_CAPACITY; i++) {
    if (cacheLastUse[i] < cacheLastUse[lru]) lru = i;
  }
  cacheKeys[lru] = key;
  cacheLastUse[lru] = nowMs();
}

static float policyScoreFloatAvg() {
  if (!hasPolicy) return 0.0f;
  float s = 0.0f;
  for (int i = 0; i < 8; i++) s += policyWeightsFloat[i];
  return s / 8.0f;
}

static int countHitsLast10() {
  int n = rollingHitCount < 10 ? rollingHitCount : 10;
  int c = 0;
  for (int i = 0; i < n; i++) if (rollingHits[i]) c++;
  return c;
}

static int countEvictionsLast10() {
  int n = rollingEvictCount < 10 ? rollingEvictCount : 10;
  int c = 0;
  for (int i = 0; i < n; i++) if (rollingEvictions[i]) c++;
  return c;
}

static int countStreamSeenLast20(const String &streamId) {
  int n = rollingReqCount < 20 ? rollingReqCount : 20;
  int c = 0;
  for (int i = 0; i < n; i++) if (rollingReq[i] == streamId) c++;
  return c;
}

static int clampInt(int x, int lo, int hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

static int state_i8_cache_occupancy() { return clampInt((cacheCount * 127) / 64, 0, 127); }
static int state_i8_latency(int latencyMs) { return clampInt((clampInt(latencyMs, 0, 2000) * 127) / 2000, 0, 127); }
static int state_i8_payload(int payloadKb) { return clampInt((clampInt(payloadKb, 0, 2000) * 127) / 2000, 0, 127); }
static int state_i8_anomaly(bool anomaly) { return anomaly ? 127 : 0; }
static int state_i8_hit_rate() { return clampInt((countHitsLast10() * 127) / 10, 0, 127); }
static int state_i8_stream_freq(const String &streamId) { return clampInt((countStreamSeenLast20(streamId) * 127) / 20, 0, 127); }
static int state_i8_time_since_last(uint32_t deltaMs) { return clampInt((clampInt((int)deltaMs, 0, 30000) * 127) / 30000, 0, 127); }
static int state_i8_cache_pressure() { return clampInt((countEvictionsLast10() * 127) / 10, 0, 127); }

static int32_t policyDotScoreInt32(int s0, int s1, int s2, int s3, int s4, int s5, int s6, int s7) {
  int s[8] = {s0, s1, s2, s3, s4, s5, s6, s7};
  int32_t score = 0;
  for (int i = 0; i < 8; i++) {
    score += (int32_t)policyWeightsInt8[i] * (int32_t)s[i];
  }
  return score;
}

static void publishTelemetry(const String &streamId, bool hit, int latencyMs, int payloadKb, bool anomaly, bool cacheDecision, bool evicted, int32_t scoreInt32) {
  StaticJsonDocument<384> doc;
  doc["node_id"] = NODE_ID;
  doc["ts_ms"] = (uint32_t)(esp_timer_get_time() / 1000ULL);
  doc["cache_hit"] = hit;
  doc["latency_ms"] = latencyMs;
  doc["stream_id"] = streamId;
  doc["cache_items"] = cacheCount;
  doc["payload_kb"] = payloadKb;
  doc["anomaly"] = anomaly;
  doc["cache_decision"] = cacheDecision;
  doc["evicted"] = evicted;
  doc["score_int32"] = (int32_t)scoreInt32;

  char out[384];
  size_t n = serializeJson(doc, out, sizeof(out));
  mqtt.publish(topicTelemetry().c_str(), out, n);
}

static void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  String t = String(topic);
  String body;
  body.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) body += (char)payload[i];

  if (t == topicPolicy()) {
    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, body);
    if (!err) {
      JsonArray wi8 = doc["int8_weights"].as<JsonArray>();
      JsonArray wf = doc["float_weights"].as<JsonArray>();
      for (int i = 0; i < 8; i++) {
        if (!wi8.isNull() && i < (int)wi8.size()) policyWeightsInt8[i] = (int8_t)wi8[i].as<int>();
        if (!wf.isNull() && i < (int)wf.size()) policyWeightsFloat[i] = wf[i].as<float>();
      }
      hasPolicy = true;
      Serial.printf("[policy] updated int8[0]=%d float_avg=%.3f\n", (int)policyWeightsInt8[0], policyScoreFloatAvg());
    }
    return;
  }

  if (t == topicRequest()) {
    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, body);
    if (err) {
      Serial.println("[request] bad json");
      return;
    }

    const char *stream = doc["stream_id"] | "";
    int payloadKb = doc["payload_kb"] | 0;
    bool anomaly = doc["anomaly"] | false;

    String streamId(stream);
    int idx = findCacheIdx(streamId);
    bool hit = idx >= 0;
    if (hit) touchCache(idx);

    // Simulated latency: local cache ~45ms, cloud fetch 800ms-2s.
    int latency = hit ? 45 : (800 + (payloadKb % 1201)); // 800..2001

    uint32_t now = nowMs();
    uint32_t delta = (lastRequestMs == 0) ? 30000 : (now - lastRequestMs);

    int s0 = state_i8_cache_occupancy();
    int s1 = state_i8_latency(latency);
    int s2 = state_i8_payload(payloadKb);
    int s3 = state_i8_anomaly(anomaly);
    int s4 = state_i8_hit_rate();
    int s5 = state_i8_stream_freq(streamId);
    int s6 = state_i8_time_since_last(delta);
    int s7 = state_i8_cache_pressure();

    int32_t score = policyDotScoreInt32(s0, s1, s2, s3, s4, s5, s6, s7);
    int32_t threshold = 0;
    bool cacheDecision = (score > threshold) || anomaly;

    bool evicted = false;
    int beforeCount = cacheCount;
    if (!hit && cacheDecision) {
      bool wasFull = (cacheCount >= CACHE_CAPACITY);
      insertCache(streamId);
      evicted = wasFull && (cacheCount == beforeCount);
    }

    Serial.printf("[req] stream=%s payload=%dKB anomaly=%d hit=%d latency=%dms cache=%d\n",
                  streamId.c_str(), payloadKb, (int)anomaly, (int)hit, latency, cacheCount);

    // Update rolling stats for next step
    rollingHits[rollingHitPos] = hit;
    rollingHitPos = (rollingHitPos + 1) % 10;
    if (rollingHitCount < 10) rollingHitCount++;

    rollingReq[rollingReqPos] = streamId;
    rollingReqPos = (rollingReqPos + 1) % 20;
    if (rollingReqCount < 20) rollingReqCount++;

    rollingEvictions[rollingEvictPos] = evicted;
    rollingEvictPos = (rollingEvictPos + 1) % 10;
    if (rollingEvictCount < 10) rollingEvictCount++;

    lastRequestMs = now;

    Serial.printf("[score] i32=%ld decision=%d s=[%d,%d,%d,%d,%d,%d,%d,%d]\n",
                  (long)score, (int)cacheDecision, s0, s1, s2, s3, s4, s5, s6, s7);

    publishTelemetry(streamId, hit, latency, payloadKb, anomaly, cacheDecision, evicted, score);
    return;
  }
}

static void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("Connecting WiFi SSID=%s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print(".");
  }
  Serial.printf("\nWiFi connected ip=%s\n", WiFi.localIP().toString().c_str());
}

static void ensureMqtt() {
  if (mqtt.connected()) return;
  while (!mqtt.connected()) {
    String cid = String("edge-") + NODE_ID + "-" + String((uint32_t)esp_random(), HEX);
    Serial.printf("Connecting MQTT %s:%d client=%s\n", MQTT_HOST, MQTT_PORT, cid.c_str());
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMqttMessage);
    if (mqtt.connect(cid.c_str())) {
      mqtt.subscribe(topicRequest().c_str(), 0);
      mqtt.subscribe(topicPolicy().c_str(), 0);
      Serial.printf("MQTT connected. Subscribed: %s, %s\n", topicRequest().c_str(), topicPolicy().c_str());
    } else {
      Serial.printf("MQTT failed rc=%d retrying...\n", mqtt.state());
      delay(1000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("Boot node_id=%s\n", NODE_ID);
  ensureWifi();
  ensureMqtt();
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();
  delay(10);
}

