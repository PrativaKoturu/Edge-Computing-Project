#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>

#ifndef NODE_ID
#define NODE_ID "zone-a"
#endif
#ifndef MQTT_HOST
#define MQTT_HOST "host.wokwi.internal"
#endif
#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif

#define LED_PIN 2
#define LCD_ADDR 0x27
#define LCD_COLS 16
#define LCD_ROWS 2

static const char *WIFI_SSID = "Wokwi-GUEST";
static const char *WIFI_PASS = "";

WiFiClient       wifiClient;
PubSubClient     mqtt(wifiClient);
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

// ── LCD helpers ───────────────────────────────────────────────────────────────
static void lcdPrint(const char *row0, const char *row1 = nullptr) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(row0);
  if (row1) {
    lcd.setCursor(0, 1);
    lcd.print(row1);
  }
}

// ── cache state ───────────────────────────────────────────────────────────────
static const int CACHE_CAPACITY = 64;
static String    cacheKeys[CACHE_CAPACITY];
static uint32_t  cacheLastUse[CACHE_CAPACITY];
static int       cacheCount = 0;

static int8_t policyWeightsInt8[8]  = {0};
static float  policyWeightsFloat[8] = {0};
static bool   hasPolicy             = false;

static bool    rollingHits[10]      = {false};
static int     rollingHitPos        = 0, rollingHitCount  = 0;
static String  rollingReq[20];
static int     rollingReqPos        = 0, rollingReqCount  = 0;
static bool    rollingEvictions[10] = {false};
static int     rollingEvictPos      = 0, rollingEvictCount = 0;
static uint32_t lastRequestMs       = 0;

static uint32_t nowMs() { return (uint32_t)millis(); }

static int findCacheIdx(const String &k) {
  for (int i = 0; i < cacheCount; i++) if (cacheKeys[i] == k) return i;
  return -1;
}
static void touchCache(int idx) { cacheLastUse[idx] = nowMs(); }
static void insertCache(const String &key) {
  int idx = findCacheIdx(key);
  if (idx >= 0) { touchCache(idx); return; }
  if (cacheCount < CACHE_CAPACITY) {
    cacheKeys[cacheCount] = key;
    cacheLastUse[cacheCount] = nowMs();
    cacheCount++; return;
  }
  int lru = 0;
  for (int i = 1; i < CACHE_CAPACITY; i++)
    if (cacheLastUse[i] < cacheLastUse[lru]) lru = i;
  cacheKeys[lru] = key; cacheLastUse[lru] = nowMs();
}

static float policyScoreFloatAvg() {
  float s = 0; for (int i = 0; i < 8; i++) s += policyWeightsFloat[i];
  return s / 8.0f;
}
static int countHitsLast10() {
  int n = min(rollingHitCount, 10), c = 0;
  for (int i = 0; i < n; i++) if (rollingHits[i]) c++;
  return c;
}
static int countEvictionsLast10() {
  int n = min(rollingEvictCount, 10), c = 0;
  for (int i = 0; i < n; i++) if (rollingEvictions[i]) c++;
  return c;
}
static int countStreamSeenLast20(const String &id) {
  int n = min(rollingReqCount, 20), c = 0;
  for (int i = 0; i < n; i++) if (rollingReq[i] == id) c++;
  return c;
}
static int clampInt(int x, int lo, int hi) { return x<lo?lo:x>hi?hi:x; }

static int si8_occ()               { return clampInt((cacheCount*127)/64,0,127); }
static int si8_lat(int ms)         { return clampInt((clampInt(ms,0,2000)*127)/2000,0,127); }
static int si8_pay(int kb)         { return clampInt((clampInt(kb,0,2000)*127)/2000,0,127); }
static int si8_anom(bool a)        { return a?127:0; }
static int si8_hit()               { return clampInt((countHitsLast10()*127)/10,0,127); }
static int si8_freq(const String &id) { return clampInt((countStreamSeenLast20(id)*127)/20,0,127); }
static int si8_tsince(uint32_t d)  { return clampInt((clampInt((int)d,0,30000)*127)/30000,0,127); }
static int si8_press()             { return clampInt((countEvictionsLast10()*127)/10,0,127); }

static int32_t policyDot(int s0,int s1,int s2,int s3,int s4,int s5,int s6,int s7) {
  int s[8]={s0,s1,s2,s3,s4,s5,s6,s7}; int32_t sc=0;
  for(int i=0;i<8;i++) sc+=(int32_t)policyWeightsInt8[i]*(int32_t)s[i];
  return sc;
}

static String topicTelemetry() { return String("edge/")+NODE_ID+"/telemetry"; }
static String topicRequest()   { return String("edge/")+NODE_ID+"/request"; }
static String topicPolicy()    { return String("edge/")+NODE_ID+"/policy"; }

static void publishTelemetry(const String &sid, bool hit, int lat, int kb,
                              bool anom, bool dec, bool evict, int32_t score) {
  JsonDocument doc;
  doc["node_id"]=NODE_ID; doc["ts_ms"]=(uint32_t)(esp_timer_get_time()/1000ULL);
  doc["cache_hit"]=hit; doc["latency_ms"]=lat; doc["stream_id"]=sid;
  doc["cache_items"]=cacheCount; doc["payload_kb"]=kb; doc["anomaly"]=anom;
  doc["cache_decision"]=dec; doc["evicted"]=evict; doc["score_int32"]=score;
  char out[384]; size_t n=serializeJson(doc,out,sizeof(out));
  mqtt.publish(topicTelemetry().c_str(),out,n);
}

static void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  String t(topic), body;
  body.reserve(length+1);
  for(unsigned int i=0;i<length;i++) body+=(char)payload[i];

  if (t == topicPolicy()) {
    JsonDocument doc;
    if (!deserializeJson(doc,body)) {
      JsonArray wi8=doc["int8_weights"].as<JsonArray>();
      JsonArray wf =doc["float_weights"].as<JsonArray>();
      for(int i=0;i<8;i++){
        if(!wi8.isNull()&&i<(int)wi8.size()) policyWeightsInt8[i]=(int8_t)wi8[i].as<int>();
        if(!wf.isNull() &&i<(int)wf.size())  policyWeightsFloat[i]=wf[i].as<float>();
      }
      hasPolicy=true;
      char buf[17]; snprintf(buf,17,"W0=%d avg=%.2f",(int)policyWeightsInt8[0],policyScoreFloatAvg());
      lcdPrint("Policy updated",buf);
      Serial.printf("[policy] int8[0]=%d avg=%.3f\n",(int)policyWeightsInt8[0],policyScoreFloatAvg());
    }
    return;
  }

  if (t == topicRequest()) {
    JsonDocument doc;
    if (deserializeJson(doc,body)) { Serial.println("[req] bad json"); return; }

    const char *stream = doc["stream_id"]|"";
    int  kb   = doc["payload_kb"]|0;
    bool anom = doc["anomaly"]|false;
    String sid(stream);

    int  idx = findCacheIdx(sid);
    bool hit = idx >= 0;
    if (hit) touchCache(idx);
    int lat = hit ? 45 : (800+(kb%1201));

    uint32_t now=nowMs(), delta=(lastRequestMs==0)?30000:(now-lastRequestMs);
    int s0=si8_occ(),s1=si8_lat(lat),s2=si8_pay(kb),s3=si8_anom(anom);
    int s4=si8_hit(),s5=si8_freq(sid),s6=si8_tsince(delta),s7=si8_press();
    int32_t score=policyDot(s0,s1,s2,s3,s4,s5,s6,s7);
    bool dec=(score>0)||anom;

    bool evict=false; int before=cacheCount;
    if(!hit&&dec){ bool full=(cacheCount>=CACHE_CAPACITY); insertCache(sid); evict=full&&(cacheCount==before); }

    rollingHits[rollingHitPos]=hit; rollingHitPos=(rollingHitPos+1)%10; if(rollingHitCount<10)rollingHitCount++;
    rollingReq[rollingReqPos]=sid; rollingReqPos=(rollingReqPos+1)%20;  if(rollingReqCount<20)rollingReqCount++;
    rollingEvictions[rollingEvictPos]=evict; rollingEvictPos=(rollingEvictPos+1)%10; if(rollingEvictCount<10)rollingEvictCount++;
    lastRequestMs=now;

    // ── LCD: row0 = sensor type + HIT/MIS, row1 = cache count + latency ──
    int sl=sid.lastIndexOf('/');
    String sensor = sl>=0 ? sid.substring(sl+1) : sid;  // "vibration","temperature","pressure"
    char row0[17], row1[17];
    snprintf(row0,17,"%-10.10s %s", sensor.c_str(), hit?"HIT":"MIS");
    snprintf(row1,17,"C:%-2d A:%d %4dms", cacheCount,(int)anom, min(lat,9999));
    lcdPrint(row0, row1);

    Serial.printf("[req]   %-22s kb=%4d hit=%d lat=%4dms cache=%d\n",
                  sid.c_str(), kb,(int)hit, lat, cacheCount);
    Serial.printf("[score] i32=%6ld dec=%d s=[%d,%d,%d,%d,%d,%d,%d,%d]\n",
                  (long)score,(int)dec,s0,s1,s2,s3,s4,s5,s6,s7);

    publishTelemetry(sid,hit,lat,kb,anom,dec,evict,score);
  }
}

static void ensureWifi() {
  if (WiFi.status()==WL_CONNECTED) return;
  lcdPrint("Connecting WiFi", WIFI_SSID);
  Serial.printf("Connecting WiFi %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID,WIFI_PASS);
  while(WiFi.status()!=WL_CONNECTED){delay(200);Serial.print(".");}
  Serial.printf("\nWiFi OK ip=%s\n",WiFi.localIP().toString().c_str());
  char buf[17]; snprintf(buf,17,"%-16s",WiFi.localIP().toString().c_str());
  lcdPrint("WiFi OK", buf);
}

static void ensureMqtt() {
  if (mqtt.connected()) return;
  mqtt.setServer(MQTT_HOST,MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(30);
  while(!mqtt.connected()){
    String cid=String("edge-")+NODE_ID+"-"+String((uint32_t)esp_random(),HEX);
    lcdPrint("Connecting MQTT", MQTT_HOST);
    Serial.printf("MQTT %s:%d id=%s\n",MQTT_HOST,MQTT_PORT,cid.c_str());
    if(mqtt.connect(cid.c_str())){
      mqtt.subscribe(topicRequest().c_str(),0);
      mqtt.subscribe(topicPolicy().c_str(),0);
      lcdPrint("MQTT OK", "Waiting data...");
      Serial.println("MQTT OK");
    } else {
      Serial.printf("MQTT fail rc=%d\n",mqtt.state());
      delay(2000);
    }
  }
}

static uint32_t ledMs=0;
static void heartbeat(){
  uint32_t n=nowMs();
  if(n-ledMs>=500){digitalWrite(LED_PIN,!digitalRead(LED_PIN));ledMs=n;}
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN,OUTPUT);
  lcd.init();
  lcd.backlight();
  lcdPrint("Edge RL " NODE_ID, "Booting...");
  delay(500);
  Serial.printf("\n=== Edge RL node=%s ===\n",NODE_ID);
  ensureWifi();
  ensureMqtt();
}

void loop() {
  heartbeat();
  ensureWifi();
  ensureMqtt();
  mqtt.loop();
  delay(10);
}
