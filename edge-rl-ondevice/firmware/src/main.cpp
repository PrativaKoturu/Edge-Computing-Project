/*
 * On-Device Q-Learning — ESP32
 * ============================================================
 * Part 2 of the Edge Computing RL project.
 *
 * Everything runs on the ESP32 itself:
 *   - Docker only sends sensor data (traffic generator)
 *   - The ESP32 trains a Q-learning policy from scratch
 *   - No central trainer, no policy push from outside
 *   - Weights update after every single request
 *
 * Algorithm: Q-Learning with linear function approximation
 *   Q(s, a) = dot(W[a], s)          // dot product of 8 weights × 8 state features
 *   TD error = r + γ·max Q(s') - Q(s,a)
 *   W[a][i] += α · tdError · s[i]   // gradient descent update
 *
 * State (8 floats, all 0–1):
 *   s[0] cache occupancy     s[1] latency norm
 *   s[2] payload norm        s[3] anomaly flag
 *   s[4] recent hit rate     s[5] stream frequency
 *   s[6] time since last req s[7] cache pressure
 *
 * Actions: 0 = skip (don't cache), 1 = cache
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>
#include <math.h>

// ── Configuration ─────────────────────────────────────────────────────────────
#ifndef NODE_ID
#define NODE_ID "edge-rl-node"
#endif
#ifndef MQTT_HOST
#define MQTT_HOST "broker.hivemq.com"
#endif
#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif

static const char *WIFI_SSID = "Wokwi-GUEST";
static const char *WIFI_PASS = "";

// ── LCD Display Setup ─────────────────────────────────────────────────────────
#define LCD_ADDR 0x27
#define LCD_COLS 16
#define LCD_ROWS 2
#define LED_PIN 13
#define BUTTON_PIN 12

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

static void lcdPrint(const char *row0, const char *row1 = nullptr) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(row0);
  if (row1) {
    lcd.setCursor(0, 1);
    lcd.print(row1);
  }
}

// ── RL Hyperparameters ────────────────────────────────────────────────────────
#define STATE_DIM 8
#define N_ACTIONS 2         // 0 = skip, 1 = cache

static float ALPHA      = 0.05f;   // learning rate — how fast weights change
static float GAMMA      = 0.95f;   // discount — how much future rewards matter
static float EPSILON    = 0.50f;   // exploration rate (starts 50%, decays to 5%)
static const float EPS_MIN   = 0.05f;
static const float EPS_DECAY = 0.001f; // subtract from epsilon each step

// ── Q-Table: W[action][state_feature] ────────────────────────────────────────
// 2 × 8 floats = 64 bytes total.  This IS the entire "neural network".
static float qW[N_ACTIONS][STATE_DIM];

// ── Training counters ─────────────────────────────────────────────────────────
static int   totalSteps    = 0;
static int   totalHits     = 0;
static float runningReward = 0.0f;

// Previous step memory (needed for TD update at next step)
static float prevState[STATE_DIM];
static int   prevAction = -1;
static bool  hasPrev    = false;

// ── LRU Cache (64 slots) ──────────────────────────────────────────────────────
static const int CACHE_CAP = 64;
static String    cacheKeys[CACHE_CAP];
static uint32_t  cacheLastUse[CACHE_CAP];
static int       cacheCount = 0;

// ── Rolling Stats ─────────────────────────────────────────────────────────────
static bool     rollingHits[10]  = {false};
static int      rollingHitPos    = 0, rollingHitCount = 0;

static String   rollingReq[20];
static int      rollingReqPos    = 0, rollingReqCount = 0;

static bool     rollingEvict[10] = {false};
static int      rollingEvictPos  = 0, rollingEvictCount = 0;

static uint32_t lastRequestMs    = 0;

// ── MQTT ──────────────────────────────────────────────────────────────────────
WiFiClient   wifiClient;
PubSubClient mqttClient(wifiClient);

static String topicRequest()   { return String("edge/") + NODE_ID + "/request"; }
static String topicTelemetry() { return String("edge/") + NODE_ID + "/telemetry"; }

// ─────────────────────────────────────────────────────────────────────────────
// LRU Cache helpers
// ─────────────────────────────────────────────────────────────────────────────
static uint32_t nowMs() { return (uint32_t)millis(); }

static int cacheFind(const String &key) {
    for (int i = 0; i < cacheCount; i++)
        if (cacheKeys[i] == key) return i;
    return -1;
}

static bool cacheInsert(const String &key) {
    // returns true if an eviction happened
    int idx = cacheFind(key);
    if (idx >= 0) { cacheLastUse[idx] = nowMs(); return false; }
    if (cacheCount < CACHE_CAP) {
        cacheKeys[cacheCount]   = key;
        cacheLastUse[cacheCount] = nowMs();
        cacheCount++;
        return false;
    }
    // evict LRU entry
    int lru = 0;
    for (int i = 1; i < CACHE_CAP; i++)
        if (cacheLastUse[i] < cacheLastUse[lru]) lru = i;
    cacheKeys[lru]    = key;
    cacheLastUse[lru] = nowMs();
    return true; // eviction happened
}

// ─────────────────────────────────────────────────────────────────────────────
// State encoding — same 8 features as Part 1 but as float 0–1
// ─────────────────────────────────────────────────────────────────────────────
static float clampF(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static float recentHitRate() {
    int n = min(rollingHitCount, 10), c = 0;
    for (int i = 0; i < n; i++) if (rollingHits[i]) c++;
    return n > 0 ? (float)c / 10.0f : 0.0f;
}

static float streamFreq(const String &id) {
    int n = min(rollingReqCount, 20), c = 0;
    for (int i = 0; i < n; i++) if (rollingReq[i] == id) c++;
    return n > 0 ? (float)c / 20.0f : 0.0f;
}

static float cachePressure() {
    int n = min(rollingEvictCount, 10), c = 0;
    for (int i = 0; i < n; i++) if (rollingEvict[i]) c++;
    return n > 0 ? (float)c / 10.0f : 0.0f;
}

static void buildState(float *s, int latencyMs, int payloadKb,
                        bool anomaly, const String &streamId) {
    uint32_t now   = nowMs();
    float deltaS   = (lastRequestMs == 0)
                     ? 30.0f
                     : clampF((now - lastRequestMs) / 1000.0f, 0.0f, 30.0f);

    s[0] = clampF((float)cacheCount / 64.0f,       0.0f, 1.0f); // cache occupancy
    s[1] = clampF((float)latencyMs  / 2000.0f,     0.0f, 1.0f); // latency
    s[2] = clampF((float)payloadKb  / 2000.0f,     0.0f, 1.0f); // payload size
    s[3] = anomaly ? 1.0f : 0.0f;                                // anomaly flag
    s[4] = recentHitRate();                                       // hit rate (last 10)
    s[5] = streamFreq(streamId);                                  // stream frequency
    s[6] = deltaS / 30.0f;                                        // time since last req
    s[7] = cachePressure();                                        // eviction pressure
}

// ─────────────────────────────────────────────────────────────────────────────
// Q-Learning core
// ─────────────────────────────────────────────────────────────────────────────

// Q(s, a) = W[a] · s  (dot product — 8 multiplications)
static float qValue(int action, float *s) {
    float q = 0.0f;
    for (int i = 0; i < STATE_DIM; i++)
        q += qW[action][i] * s[i];
    return q;
}

// Epsilon-greedy action selection
static int selectAction(float *s) {
    float r = (float)(esp_random() % 10000) / 10000.0f;
    if (r < EPSILON)
        return (int)(esp_random() % N_ACTIONS); // explore: random
    // exploit: pick action with higher Q value
    return (qValue(1, s) >= qValue(0, s)) ? 1 : 0;
}

// TD(0) update: Q(s,a) += alpha * (r + gamma * max_a' Q(s',a') - Q(s,a)) * s
static float tdUpdate(float *s, int action, float reward, float *sNext) {
    float qCurr    = qValue(action, s);
    float qNext    = fmaxf(qValue(0, sNext), qValue(1, sNext));
    float tdError  = reward + GAMMA * qNext - qCurr;

    for (int i = 0; i < STATE_DIM; i++)
        qW[action][i] += ALPHA * tdError * s[i];

    // decay epsilon toward EPS_MIN
    EPSILON = fmaxf(EPS_MIN, EPSILON - EPS_DECAY);
    return tdError;
}

// Reward: same formula as the central trainer in Part 1
static float computeReward(bool hit, int latencyMs, bool anomaly, float pressure) {
    float r = hit ? 1.0f : -1.0f;
    r -= 0.001f * (float)latencyMs;
    if (anomaly && hit) r += 0.5f;
    r -= 0.3f * pressure;
    return r;
}

// ─────────────────────────────────────────────────────────────────────────────
// Telemetry publish — sends learning stats back so monitor.py can plot them
// ─────────────────────────────────────────────────────────────────────────────
static void publishTelemetry(const String &streamId, bool hit, int latencyMs,
                              int payloadKb, bool anomaly, bool decision,
                              bool evicted, float reward, float tdErr) {
    StaticJsonDocument<512> doc;
    doc["node_id"]       = NODE_ID;
    doc["ts_ms"]         = (uint32_t)(esp_timer_get_time() / 1000ULL);
    doc["cache_hit"]     = hit;
    doc["latency_ms"]    = latencyMs;
    doc["stream_id"]     = streamId;
    doc["cache_items"]   = cacheCount;
    doc["payload_kb"]    = payloadKb;
    doc["anomaly"]       = anomaly;
    doc["cache_decision"]= decision;
    doc["evicted"]       = evicted;
    doc["reward"]        = reward;
    doc["td_error"]      = tdErr;
    doc["epsilon"]       = EPSILON;
    doc["total_steps"]   = totalSteps;
    doc["hit_rate"]      = totalSteps > 0
                           ? (float)totalHits / (float)totalSteps
                           : 0.0f;
    char buf[512];
    size_t n = serializeJson(doc, buf, sizeof(buf));
    mqttClient.publish(topicTelemetry().c_str(), buf, n);
}

// ─────────────────────────────────────────────────────────────────────────────
// MQTT message handler — called for every incoming request
// ─────────────────────────────────────────────────────────────────────────────
static void onMessage(char *topic, byte *payload, unsigned int len) {
    String body;
    body.reserve(len + 1);
    for (unsigned int i = 0; i < len; i++) body += (char)payload[i];

    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, body)) {
        Serial.println("[req] bad json — skipping");
        return;
    }

    const char *stream = doc["stream_id"] | "";
    int  payloadKb     = doc["payload_kb"] | 0;
    bool anomaly       = doc["anomaly"]    | false;
    String streamId(stream);

    // ── 1. Check cache (hit/miss determined by PREVIOUS caching decisions) ───
    int  idx       = cacheFind(streamId);
    bool hit       = (idx >= 0);
    if (hit) cacheLastUse[idx] = nowMs();
    int  latencyMs = hit ? 45 : (800 + (payloadKb % 1201));

    // ── 2. Build current state ───────────────────────────────────────────────
    float curState[STATE_DIM];
    buildState(curState, latencyMs, payloadKb, anomaly, streamId);

    // ── 3. TD update using reward from THIS step + previous (s, a) ──────────
    float reward = 0.0f, tdErr = 0.0f;
    if (hasPrev) {
        reward = computeReward(hit, latencyMs, anomaly, cachePressure());
        tdErr  = tdUpdate(prevState, prevAction, reward, curState);
        runningReward = 0.99f * runningReward + 0.01f * reward;
    }

    // ── 4. Select action for THIS request (affects future hits) ─────────────
    int  action       = selectAction(curState);
    bool cacheDecision = (action == 1) || anomaly; // always cache anomalies

    // ── 5. Execute action ────────────────────────────────────────────────────
    bool evicted = false;
    if (!hit && cacheDecision)
        evicted = cacheInsert(streamId);

    // ── 6. Update rolling stats ──────────────────────────────────────────────
    rollingHits[rollingHitPos]   = hit;
    rollingHitPos                = (rollingHitPos   + 1) % 10;
    if (rollingHitCount   < 10)  rollingHitCount++;

    rollingReq[rollingReqPos]    = streamId;
    rollingReqPos                = (rollingReqPos   + 1) % 20;
    if (rollingReqCount   < 20)  rollingReqCount++;

    rollingEvict[rollingEvictPos] = evicted;
    rollingEvictPos               = (rollingEvictPos + 1) % 10;
    if (rollingEvictCount < 10)  rollingEvictCount++;

    lastRequestMs = nowMs();
    if (hit) totalHits++;
    totalSteps++;

    // ── 7. Save (curState, action) for next TD update ────────────────────────
    memcpy(prevState, curState, sizeof(float) * STATE_DIM);
    prevAction = action;
    hasPrev    = true;

    // ── 8. Serial output ─────────────────────────────────────────────────────
    float hitRate = totalSteps > 0 ? (float)totalHits / (float)totalSteps * 100.0f : 0.0f;

    // Update LCD display with current status
    char lcdLine1[17], lcdLine2[17];
    snprintf(lcdLine1, sizeof(lcdLine1), "Steps:%d Hit:%d%%", totalSteps, (int)hitRate);
    snprintf(lcdLine2, sizeof(lcdLine2), "Cache:%d Eps:%.2f", cacheCount, EPSILON);
    lcdPrint(lcdLine1, lcdLine2);

    Serial.printf("[req]     stream=%-30s  hit=%d  lat=%4dms  cache=%2d\n",
                  streamId.c_str(), (int)hit, latencyMs, cacheCount);
    if (hasPrev && totalSteps > 1) {
        Serial.printf("[learn]   action=%-5s  reward=%+.3f  td_err=%+.4f  eps=%.3f  hit_rate=%.1f%%\n",
                      cacheDecision ? "CACHE" : "SKIP",
                      reward, tdErr, EPSILON, hitRate);
    }

    // Print full weight vector every 50 steps so you can watch them change
    if (totalSteps % 50 == 0) {
        Serial.printf("[weights] step=%d  eps=%.3f  hit_rate=%.1f%%\n",
                      totalSteps, EPSILON, hitRate);
        Serial.printf("  W[CACHE]: ");
        for (int i = 0; i < STATE_DIM; i++)
            Serial.printf("%+.4f  ", qW[1][i]);
        Serial.println();
        Serial.printf("  W[SKIP]:  ");
        for (int i = 0; i < STATE_DIM; i++)
            Serial.printf("%+.4f  ", qW[0][i]);
        Serial.println();
    }

    publishTelemetry(streamId, hit, latencyMs, payloadKb, anomaly,
                     cacheDecision, evicted, reward, tdErr);
}

// ─────────────────────────────────────────────────────────────────────────────
// WiFi + MQTT connection management
// ─────────────────────────────────────────────────────────────────────────────
static void ensureWifi() {
    if (WiFi.status() == WL_CONNECTED) return;
    Serial.printf("[wifi] Connecting to %s ", WIFI_SSID);
    lcdPrint("WiFi", "Connecting...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
    Serial.printf("\n[wifi] Connected  ip=%s\n", WiFi.localIP().toString().c_str());
    lcdPrint("WiFi OK", WiFi.localIP().toString().c_str());
    delay(1500);
}

static void ensureMqtt() {
    if (mqttClient.connected()) return;
    lcdPrint("MQTT", "Connecting...");
    mqttClient.setServer(MQTT_HOST, MQTT_PORT);
    mqttClient.setCallback(onMessage);
    while (!mqttClient.connected()) {
        String cid = String("edge-rl-") + String((uint32_t)esp_random(), HEX);
        Serial.printf("[mqtt] Connecting %s:%d  id=%s\n", MQTT_HOST, MQTT_PORT, cid.c_str());
        if (mqttClient.connect(cid.c_str())) {
            mqttClient.subscribe(topicRequest().c_str(), 0);
            Serial.printf("[mqtt] Connected.  Subscribed: %s\n", topicRequest().c_str());
            lcdPrint("MQTT OK", "Ready!");
            delay(1500);
        } else {
            Serial.printf("[mqtt] Failed rc=%d  retrying in 2s...\n", mqttClient.state());
            delay(2000);
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arduino entry points
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);
    
    // Initialize LCD
    lcd.init();
    lcd.backlight();
    lcdPrint("Edge RL Node", "Initializing...");
    
    // Force flush and simple test print
    Serial.println("");
    Serial.println("START");
    Serial.flush();
    delay(100);

    Serial.println("\n========================================");
    Serial.printf(" On-Device Q-Learning  [%s]\n", NODE_ID);
    Serial.println("========================================");
    Serial.printf(" alpha=%.3f  gamma=%.3f  eps=%.2f  state=%dD\n",
                  ALPHA, GAMMA, EPSILON, STATE_DIM);
    Serial.println(" Training happens entirely on this ESP32.");
    Serial.println(" No central trainer. No pushed weights.");
    Serial.println("========================================\n");

    // Initialise Q-weights to tiny random values near zero
    for (int a = 0; a < N_ACTIONS; a++)
        for (int i = 0; i < STATE_DIM; i++)
            qW[a][i] = ((int)(esp_random() % 200) - 100) * 0.0001f; // [-0.01, +0.01]

    ensureWifi();
    ensureMqtt();
}

void loop() {
    ensureWifi();
    ensureMqtt();
    mqttClient.loop();
    delay(10);
}
