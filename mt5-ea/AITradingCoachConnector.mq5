//+------------------------------------------------------------------+
//| AI Trading Coach Connector                                      |
//| V2 panel can trade only after backend pre-trade approval.         |
//+------------------------------------------------------------------+
#property strict
#property version   "0.2"
#property description "Send MT5 telemetry and optional panel trade requests to AI Trading Coach backend."
#property description "Whitelist BackendURL in MT5: Tools -> Options -> Expert Advisors -> Allow WebRequest for listed URL."

#include <Trade/Trade.mqh>

input string BackendURL = "http://127.0.0.1:8000";
input string ApiKey = "change-me";
input int SendIntervalSeconds = 10;
input bool SafeMode = true;
input bool AllowCloseAll = false;
input bool UseRiskPositionSizing = true;
input bool AutoTPByRR = true;
input double DefaultRiskPercent = 1.0;
input double DefaultRR = 2.0;
input string OrderHotkey = "t";
input ulong MagicNumber = 260629;

CTrade Trade;

string PANEL_PREFIX = "ATC_PANEL_";
string LINE_PREFIX = "ATC_LINE_";
string OBJ_ENTRY = "ATC_PANEL_ENTRY";
string OBJ_LOT = "ATC_PANEL_LOT";
string OBJ_RISK = "ATC_PANEL_RISK";
string OBJ_RR = "ATC_PANEL_RR";
string OBJ_SL = "ATC_PANEL_SL";
string OBJ_TP = "ATC_PANEL_TP";
string OBJ_BUY = "ATC_PANEL_BUY";
string OBJ_SELL = "ATC_PANEL_SELL";
string OBJ_CLOSE_ALL = "ATC_PANEL_CLOSE_ALL";
string OBJ_AUTO_TP = "ATC_PANEL_AUTO_TP";
string OBJ_HOTKEY = "ATC_PANEL_HOTKEY";
string OBJ_STATUS = "ATC_PANEL_STATUS";
string OBJ_PLAN = "ATC_PANEL_PLAN";
string LINE_ENTRY = "ATC_LINE_ENTRY";
string LINE_SL = "ATC_LINE_SL";
string LINE_TP = "ATC_LINE_TP";
string LastHttpError = "";
bool LastHttpConnectivityError = false;
string PlanDirection = "BUY";
bool AutoTPEnabled = true;
ulong LastClickTick = 0;

string NormalizeBaseUrl(string url)
{
   string clean = url;
   while(StringLen(clean) > 0 && StringSubstr(clean, StringLen(clean) - 1, 1) == "/")
      clean = StringSubstr(clean, 0, StringLen(clean) - 1);
   return clean;
}

string AlternateLocalBaseUrl(string url)
{
   string clean = NormalizeBaseUrl(url);
   string alternate = clean;
   if(StringFind(clean, "localhost") >= 0)
      StringReplace(alternate, "localhost", "127.0.0.1");
   else if(StringFind(clean, "127.0.0.1") >= 0)
      StringReplace(alternate, "127.0.0.1", "localhost");
   else
      alternate = "";
   return alternate;
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   return value;
}

string JsonNumberOrNull(double value, int digits = 5)
{
   if(value == EMPTY_VALUE || !MathIsValidNumber(value))
      return "null";
   return DoubleToString(value, digits);
}

string IsoTime(datetime value)
{
   MqlDateTime dt;
   TimeToStruct(value, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

bool SendJsonToBackend(string endpoint, string json)
{
   string body = "";
   int status = 0;
   return PostJsonToBackend(endpoint, json, body, status);
}

bool IsHttpStatusCode(int code)
{
   return code >= 100 && code <= 599;
}

string TruncateText(string value, int max_len)
{
   if(StringLen(value) <= max_len)
      return value;
   return StringSubstr(value, 0, max_len - 3) + "...";
}

string JsonKeyMarker(string key)
{
   return "\"" + key + "\"";
}

int JsonValueStart(string json, string key)
{
   string marker = JsonKeyMarker(key);
   int start = StringFind(json, marker);
   if(start < 0)
      return -1;
   start = StringFind(json, ":", start + StringLen(marker));
   if(start < 0)
      return -1;
   start++;
   while(start < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, start);
      if(ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n')
         break;
      start++;
   }
   return start;
}

string HttpFailureMessage(string endpoint, int http_status, string body)
{
   if(http_status == 401)
      return "Backend returned 401: invalid x-api-key.";
   if(http_status == 404)
      return "Backend returned 404: account not found or endpoint unavailable. Send heartbeat first and check backend URL.";
   if(http_status == 422)
      return "Backend returned 422: invalid pre-trade payload. Body: " + TruncateText(body, 220);
   if(http_status >= 500)
      return StringFormat("Backend returned %d: server error. Body: %s", http_status, TruncateText(body, 220));
   return StringFormat("Backend returned %d from %s. Body: %s", http_status, endpoint, TruncateText(body, 220));
}

bool PostJsonToBackend(string endpoint, string json, string &body, int &http_status)
{
   LastHttpError = "";
   LastHttpConnectivityError = false;
   string url = NormalizeBaseUrl(BackendURL) + endpoint;
   if(PostJsonToUrl(url, endpoint, json, body, http_status))
      return true;

   string first_error = LastHttpError;
   string alternate_base = AlternateLocalBaseUrl(BackendURL);
   if(LastHttpConnectivityError && alternate_base != "")
   {
      string alternate_url = alternate_base + endpoint;
      PrintFormat("AITradingCoach retrying alternate local URL: %s", alternate_url);
      if(PostJsonToUrl(alternate_url, endpoint, json, body, http_status))
         return true;
      LastHttpError = first_error + " Alternate failed: " + LastHttpError;
   }
   return false;
}

bool PostJsonToUrl(string url, string endpoint, string json, string &body, int &http_status)
{
   string headers = "Content-Type: application/json\r\nx-api-key: " + ApiKey + "\r\n";
   char post[];
   char result[];
   string result_headers;

   StringToCharArray(json, post, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(post) > 0)
      ArrayResize(post, ArraySize(post) - 1);

   ResetLastError();
   PrintFormat("AITradingCoach WebRequest URL: %s", url);
   PrintFormat("AITradingCoach WebRequest headers: %s", headers);
   PrintFormat("AITradingCoach WebRequest JSON body: %s", json);
   int webrequest_code = WebRequest("POST", url, headers, 10000, post, result, result_headers);
   int last_error = GetLastError();
   body = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   http_status = IsHttpStatusCode(webrequest_code) ? webrequest_code : 0;

   PrintFormat("AITradingCoach WebRequest return code: %d", webrequest_code);
   PrintFormat("AITradingCoach HTTP response code: %d", http_status);
   PrintFormat("AITradingCoach GetLastError: %d", last_error);
   PrintFormat("AITradingCoach response headers: %s", result_headers);
   PrintFormat("AITradingCoach response body: %s", body);

   if(webrequest_code == -1)
   {
      LastHttpConnectivityError = true;
      LastHttpError = StringFormat("Backend unreachable: check WebRequest permission or backend URL. URL=%s GetLastError=%d.", url, last_error);
      PrintFormat("AITradingCoach %s", LastHttpError);
      return false;
   }

   if(!IsHttpStatusCode(webrequest_code))
   {
      LastHttpConnectivityError = true;
      LastHttpError = StringFormat("Backend unreachable: WebRequest returned non-HTTP code %d. Check WebRequest permission or backend URL %s.", webrequest_code, url);
      PrintFormat("AITradingCoach %s", LastHttpError);
      return false;
   }

   if(http_status < 200 || http_status >= 300)
   {
      LastHttpConnectivityError = false;
      LastHttpError = HttpFailureMessage(endpoint, http_status, body);
      PrintFormat("AITradingCoach %s", LastHttpError);
      return false;
   }

   PrintFormat("AITradingCoach sent %s successfully. HTTP %d", endpoint, http_status);
   return true;
}

string JsonStringValue(string json, string key)
{
   int start = JsonValueStart(json, key);
   if(start < 0)
      return "";
   if(StringGetCharacter(json, start) != '"')
      return "";
   start++;
   int end = start;
   bool escaped = false;
   while(end < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end);
      if(ch == '\\' && !escaped)
      {
         escaped = true;
         end++;
         continue;
      }
      if(ch == '"' && !escaped)
         break;
      escaped = false;
      end++;
   }
   if(end < 0)
      return "";
   string value = StringSubstr(json, start, end - start);
   StringReplace(value, "\\\"", "\"");
   StringReplace(value, "\\n", "\n");
   StringReplace(value, "\\r", "\r");
   StringReplace(value, "\\\\", "\\");
   return value;
}

bool JsonBoolValue(string json, string key)
{
   int start = JsonValueStart(json, key);
   if(start < 0)
      return false;
   string value = StringSubstr(json, start, 5);
   return StringFind(value, "true") == 0;
}

bool JsonHasKey(string json, string key)
{
   return JsonValueStart(json, key) >= 0;
}

double MovingAverageValue(string symbol, ENUM_TIMEFRAMES timeframe, int period, int shift)
{
   int handle = iMA(symbol, timeframe, period, 0, MODE_EMA, PRICE_CLOSE);
   if(handle == INVALID_HANDLE)
      return EMPTY_VALUE;

   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(handle, 0, shift, 1, buffer) <= 0)
   {
      IndicatorRelease(handle);
      return EMPTY_VALUE;
   }
   IndicatorRelease(handle);
   return buffer[0];
}

void SendHeartbeat()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string json = StringFormat(
      "{\"account_number\":\"%I64d\",\"broker\":\"%s\",\"server\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"timestamp\":\"%s\"}",
      login,
      JsonEscape(AccountInfoString(ACCOUNT_COMPANY)),
      JsonEscape(AccountInfoString(ACCOUNT_SERVER)),
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoDouble(ACCOUNT_MARGIN),
      AccountInfoDouble(ACCOUNT_FREEMARGIN),
      IsoTime(TimeCurrent())
   );

   SendJsonToBackend("/api/mt5/heartbeat", json);
}

string EventTypeFromTransaction(const MqlTradeTransaction &trans)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      if(trans.deal > 0 && HistoryDealSelect(trans.deal))
      {
         long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
            return "order_closed";
         if(entry == DEAL_ENTRY_IN || entry == DEAL_ENTRY_INOUT)
            return "order_opened";
      }
      return "position_updated";
   }
   if(trans.type == TRADE_TRANSACTION_ORDER_ADD)
      return "order_opened";
   if(trans.type == TRADE_TRANSACTION_ORDER_UPDATE)
      return "order_modified";
   if(trans.type == TRADE_TRANSACTION_POSITION)
      return "position_updated";
   return "position_updated";
}

void SendTradeEvent(const MqlTradeTransaction &trans, const MqlTradeRequest &request)
{
   string symbol = trans.symbol;
   if(symbol == "")
      symbol = request.symbol;

   double profit = 0.0;
   double commission = 0.0;
   double swap = 0.0;
   datetime close_time = 0;

   if(trans.deal > 0 && HistoryDealSelect(trans.deal))
   {
      profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
      commission = HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
      swap = HistoryDealGetDouble(trans.deal, DEAL_SWAP);
      close_time = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);
   }

   double sl = trans.price_sl;
   double tp = trans.price_tp;
   double close_price = (close_time > 0 ? trans.price : 0.0);
   string close_time_json = (close_time > 0 ? "\"" + IsoTime(close_time) + "\"" : "null");

   string json = StringFormat(
      "{\"account_number\":\"%I64d\",\"event_type\":\"%s\",\"symbol\":\"%s\",\"ticket\":\"%I64d\",\"order_type\":\"%s\",\"lot\":%.2f,\"entry_price\":%.5f,\"sl\":%s,\"tp\":%s,\"close_price\":%s,\"profit\":%.2f,\"commission\":%.2f,\"swap\":%.2f,\"open_time\":\"%s\",\"close_time\":%s}",
      AccountInfoInteger(ACCOUNT_LOGIN),
      EventTypeFromTransaction(trans),
      JsonEscape(symbol),
      (long)(trans.order > 0 ? trans.order : trans.position),
      JsonEscape(EnumToString(request.type)),
      trans.volume,
      trans.price,
      (sl > 0.0 ? DoubleToString(sl, 5) : "null"),
      (tp > 0.0 ? DoubleToString(tp, 5) : "null"),
      (close_price > 0.0 ? DoubleToString(close_price, 5) : "null"),
      profit,
      commission,
      swap,
      IsoTime(TimeCurrent()),
      close_time_json
   );

   SendJsonToBackend("/api/mt5/trade-event", json);
}

void SetStatus(string message, color text_color = clrWhite)
{
   ObjectSetString(0, OBJ_STATUS, OBJPROP_TEXT, "Risk Status: " + message);
   ObjectSetInteger(0, OBJ_STATUS, OBJPROP_COLOR, text_color);
   Print("AITradingCoach status: " + message);
}

void CreatePanelLabel(string name, string text, int x, int y, int width, color text_color = clrWhite)
{
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, width);
   ObjectSetInteger(0, name, OBJPROP_COLOR, text_color);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void CreatePanelEdit(string name, string text, int x, int y, int width)
{
   ObjectCreate(0, name, OBJ_EDIT, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, width);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, 22);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, clrWhite);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrBlack);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void CreatePanelButton(string name, string text, int x, int y, int width, color bg_color)
{
   ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, width);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, 24);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg_color);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrWhite);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

double NormalizePrice(double price)
{
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_size > 0.0)
      price = MathRound(price / tick_size) * tick_size;
   return NormalizeDouble(price, _Digits);
}

double NormalizeVolume(double volume)
{
   double min_volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;

   volume = MathFloor(volume / step) * step;
   if(volume < min_volume)
      volume = min_volume;
   if(max_volume > 0.0 && volume > max_volume)
      volume = max_volume;
   return NormalizeDouble(volume, 2);
}

double PriceLineValue(string line_name)
{
   if(ObjectFind(0, line_name) < 0)
      return 0.0;
   return NormalizePrice(ObjectGetDouble(0, line_name, OBJPROP_PRICE));
}

void CreatePriceLine(string name, string text, double price, color line_color)
{
   if(ObjectFind(0, name) >= 0)
      ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, line_color);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTED, true);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void ResetButtonStates()
{
   ObjectSetInteger(0, OBJ_BUY, OBJPROP_STATE, false);
   ObjectSetInteger(0, OBJ_SELL, OBJPROP_STATE, false);
   ObjectSetInteger(0, OBJ_CLOSE_ALL, OBJPROP_STATE, false);
   ObjectSetInteger(0, OBJ_AUTO_TP, OBJPROP_STATE, false);
   ChartRedraw();
}

void UpdateAutoTPButton()
{
   ObjectSetString(0, OBJ_AUTO_TP, OBJPROP_TEXT, AutoTPEnabled ? "AUTO TP ON" : "AUTO TP OFF");
   ObjectSetInteger(0, OBJ_AUTO_TP, OBJPROP_BGCOLOR, AutoTPEnabled ? clrDarkGreen : clrDimGray);
}

int HotkeyCharCode()
{
   if(StringLen(OrderHotkey) <= 0)
      return 0;

   int code = (int)StringGetCharacter(OrderHotkey, 0);
   if(code >= 97 && code <= 122)
      code -= 32;
   return code;
}

bool IsOrderHotkey(int key_code)
{
   int configured = HotkeyCharCode();
   if(configured <= 0)
      return false;

   if(key_code >= 97 && key_code <= 122)
      key_code -= 32;
   return key_code == configured;
}

void SetEditText(string object_name, double value)
{
   ObjectSetString(0, object_name, OBJPROP_TEXT, DoubleToString(NormalizePrice(value), _Digits));
}

bool IsValidPlan(string order_type, double entry, double sl, double tp, string &reason)
{
   if(entry <= 0.0)
   {
      reason = "Entry must be greater than 0.";
      return false;
   }
   if(sl <= 0.0)
   {
      reason = "SL must be greater than 0.";
      return false;
   }
   if(order_type == "BUY" && sl >= entry)
   {
      reason = "For BUY, SL must be below Entry.";
      return false;
   }
   if(order_type == "SELL" && sl <= entry)
   {
      reason = "For SELL, SL must be above Entry.";
      return false;
   }
   if(tp > 0.0)
   {
      if(order_type == "BUY" && tp <= entry)
      {
         reason = "For BUY, TP must be above Entry.";
         return false;
      }
      if(order_type == "SELL" && tp >= entry)
      {
         reason = "For SELL, TP must be below Entry.";
         return false;
      }
   }
   return true;
}

double CalculateRiskLot(string order_type, double entry, double sl)
{
   double risk_percent = StringToDouble(ObjectGetString(0, OBJ_RISK, OBJPROP_TEXT));
   if(risk_percent <= 0.0)
      risk_percent = DefaultRiskPercent;

   double risk_money = AccountInfoDouble(ACCOUNT_EQUITY) * risk_percent / 100.0;
   ENUM_ORDER_TYPE calc_type = (order_type == "BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double loss_for_one_lot = 0.0;
   if(!OrderCalcProfit(calc_type, _Symbol, 1.0, entry, sl, loss_for_one_lot))
   {
      PrintFormat("AITradingCoach OrderCalcProfit failed: %d", GetLastError());
      return NormalizeVolume(PanelDouble(OBJ_LOT));
   }

   loss_for_one_lot = MathAbs(loss_for_one_lot);
   if(loss_for_one_lot <= 0.0)
      return NormalizeVolume(PanelDouble(OBJ_LOT));

   return NormalizeVolume(risk_money / loss_for_one_lot);
}

double CalculateRiskAmount(string order_type, double lot, double entry, double sl)
{
   if(lot <= 0.0 || entry <= 0.0 || sl <= 0.0)
      return 0.0;

   ENUM_ORDER_TYPE calc_type = (order_type == "BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double loss = 0.0;
   if(!OrderCalcProfit(calc_type, _Symbol, lot, entry, sl, loss))
   {
      PrintFormat("AITradingCoach OrderCalcProfit risk amount failed: %d", GetLastError());
      return 0.0;
   }
   return MathAbs(loss);
}

void UpdateRRFromLines()
{
   double entry = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   double tp = PriceLineValue(LINE_TP);
   double risk = MathAbs(entry - sl);
   double reward = MathAbs(tp - entry);
   if(entry > 0.0 && sl > 0.0 && tp > 0.0 && risk > 0.0)
      ObjectSetString(0, OBJ_RR, OBJPROP_TEXT, DoubleToString(reward / risk, 2));
}

string DirectionFromEntrySL()
{
   double entry = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   if(entry <= 0.0 || sl <= 0.0)
      return PlanDirection;
   if(sl > entry)
      return "SELL";
   if(sl < entry)
      return "BUY";
   return PlanDirection;
}

void SyncDirectionFromEntrySL()
{
   PlanDirection = DirectionFromEntrySL();
}

void UpdateTPFromRR(string order_type)
{
   double rr = StringToDouble(ObjectGetString(0, OBJ_RR, OBJPROP_TEXT));
   if(rr <= 0.0)
      rr = DefaultRR;

   double entry = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   double risk = MathAbs(entry - sl);
   if(entry <= 0.0 || sl <= 0.0 || risk <= 0.0)
      return;

   double tp = (order_type == "BUY" ? entry + risk * rr : entry - risk * rr);
   tp = NormalizePrice(tp);
   ObjectSetDouble(0, LINE_TP, OBJPROP_PRICE, tp);
   SetEditText(OBJ_TP, tp);
}

void RefreshPlannerFromLines(bool update_rr = true)
{
   double entry = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   double tp = PriceLineValue(LINE_TP);
   SetEditText(OBJ_ENTRY, entry);
   SetEditText(OBJ_SL, sl);
   SetEditText(OBJ_TP, tp);
   if(update_rr)
      UpdateRRFromLines();

   string reason = "";
   double lot = UseRiskPositionSizing ? CalculateRiskLot(PlanDirection, entry, sl) : NormalizeVolume(PanelDouble(OBJ_LOT));
   if(UseRiskPositionSizing)
      ObjectSetString(0, OBJ_LOT, OBJPROP_TEXT, DoubleToString(lot, 2));
   if(IsValidPlan(PlanDirection, entry, sl, tp, reason))
      ObjectSetString(0, OBJ_PLAN, OBJPROP_TEXT, StringFormat("Plan: %s | RR %s | Risk %s%% | Lot %.2f", PlanDirection, ObjectGetString(0, OBJ_RR, OBJPROP_TEXT), ObjectGetString(0, OBJ_RISK, OBJPROP_TEXT), lot));
   else
      ObjectSetString(0, OBJ_PLAN, OBJPROP_TEXT, "Plan: " + reason);
   ChartRedraw();
}

void RefreshLinesFromEdits(bool auto_tp_after = false)
{
   double entry = NormalizePrice(StringToDouble(ObjectGetString(0, OBJ_ENTRY, OBJPROP_TEXT)));
   double sl = NormalizePrice(StringToDouble(ObjectGetString(0, OBJ_SL, OBJPROP_TEXT)));
   double tp = NormalizePrice(StringToDouble(ObjectGetString(0, OBJ_TP, OBJPROP_TEXT)));
   if(entry > 0.0)
      ObjectSetDouble(0, LINE_ENTRY, OBJPROP_PRICE, entry);
   if(sl > 0.0)
      ObjectSetDouble(0, LINE_SL, OBJPROP_PRICE, sl);
   if(tp > 0.0)
      ObjectSetDouble(0, LINE_TP, OBJPROP_PRICE, tp);
   if(auto_tp_after && AutoTPEnabled)
   {
      SyncDirectionFromEntrySL();
      UpdateTPFromRR(PlanDirection);
      RefreshPlannerFromLines(false);
   }
   else
      RefreshPlannerFromLines();
}

void ApplyAutoTPFromRR()
{
   if(!AutoTPEnabled)
      return;
   SyncDirectionFromEntrySL();
   UpdateTPFromRR(PlanDirection);
   RefreshPlannerFromLines(false);
}

void ToggleAutoTP()
{
   AutoTPEnabled = !AutoTPEnabled;
   UpdateAutoTPButton();
   ApplyAutoTPFromRR();
   RefreshPlannerFromLines(false);
}

void CreateTradeLines()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double entry = NormalizePrice((bid + ask) / 2.0);
   if(entry <= 0.0)
      entry = NormalizePrice(iClose(_Symbol, PERIOD_CURRENT, 0));
   double default_distance = MathMax(100.0 * _Point, SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE) * 100.0);
   double sl = NormalizePrice(entry - default_distance);
   double tp = NormalizePrice(entry + default_distance * DefaultRR);

   CreatePriceLine(LINE_ENTRY, "ATC Entry", entry, clrDodgerBlue);
   CreatePriceLine(LINE_SL, "ATC Stop Loss", sl, clrTomato);
   CreatePriceLine(LINE_TP, "ATC Take Profit", tp, clrLimeGreen);
}

void CreateTradePanel()
{
   CreatePanelLabel(PANEL_PREFIX + "TITLE", SafeMode ? "AI Trading Coach Panel (SAFE)" : "AI Trading Coach Panel (LIVE)", 12, 18, 260, SafeMode ? clrGold : clrLime);
   CreatePanelLabel(PANEL_PREFIX + "ENTRY_LABEL", "Entry", 12, 45, 40);
   CreatePanelEdit(OBJ_ENTRY, "0", 58, 42, 92);
   CreatePanelLabel(PANEL_PREFIX + "SL_LABEL", "SL", 160, 45, 25);
   CreatePanelEdit(OBJ_SL, "0", 190, 42, 92);
   CreatePanelLabel(PANEL_PREFIX + "TP_LABEL", "TP", 292, 45, 25);
   CreatePanelEdit(OBJ_TP, "0", 322, 42, 92);
   CreatePanelLabel(PANEL_PREFIX + "RISK_LABEL", "Risk %", 12, 74, 50);
   CreatePanelEdit(OBJ_RISK, DoubleToString(DefaultRiskPercent, 2), 70, 71, 58);
   CreatePanelLabel(PANEL_PREFIX + "RR_LABEL", "RR", 138, 74, 25);
   CreatePanelEdit(OBJ_RR, DoubleToString(DefaultRR, 2), 166, 71, 58);
   CreatePanelLabel(PANEL_PREFIX + "LOT_LABEL", "Lot", 234, 74, 30);
   CreatePanelEdit(OBJ_LOT, "0.10", 266, 71, 58);
   CreatePanelButton(OBJ_AUTO_TP, AutoTPEnabled ? "AUTO TP ON" : "AUTO TP OFF", 334, 71, 94, AutoTPEnabled ? clrDarkGreen : clrDimGray);
   CreatePanelButton(OBJ_BUY, "BUY", 12, 104, 78, clrSeaGreen);
   CreatePanelButton(OBJ_SELL, "SELL", 98, 104, 78, clrFireBrick);
   CreatePanelButton(OBJ_CLOSE_ALL, "CLOSE ALL", 184, 104, 100, clrDimGray);
   CreatePanelLabel(OBJ_HOTKEY, "Hotkey: " + OrderHotkey, 294, 109, 120, clrSilver);
   CreatePanelLabel(OBJ_PLAN, "Plan: waiting", 12, 136, 520, clrDeepSkyBlue);
   CreatePanelLabel(OBJ_STATUS, "Risk Status: waiting", 12, 156, 520, clrWhite);
   CreateTradeLines();
   RefreshPlannerFromLines();
   ChartRedraw();
}

void DeleteTradePanel()
{
   ObjectsDeleteAll(0, PANEL_PREFIX);
   ObjectsDeleteAll(0, LINE_PREFIX);
}

double PanelDouble(string object_name)
{
   return StringToDouble(ObjectGetString(0, object_name, OBJPROP_TEXT));
}

bool RunPreTradeCheck(string order_type, double lot, double entry_price, double sl, double tp, string &reason)
{
   string sl_json = (sl > 0.0 ? DoubleToString(sl, _Digits) : "null");
   string tp_json = (tp > 0.0 ? DoubleToString(tp, _Digits) : "null");
   double risk_amount = CalculateRiskAmount(order_type, lot, entry_price, sl);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double risk_percent = (equity > 0.0 && risk_amount > 0.0 ? risk_amount / equity * 100.0 : 0.0);
   string risk_amount_json = (risk_amount > 0.0 ? DoubleToString(risk_amount, 2) : "null");
   string risk_percent_json = (risk_percent > 0.0 ? DoubleToString(risk_percent, 4) : "null");
   string json = StringFormat(
      "{\"account_number\":\"%I64d\",\"symbol\":\"%s\",\"order_type\":\"%s\",\"lot\":%.2f,\"entry_price\":%s,\"sl\":%s,\"tp\":%s,\"risk_percent\":%s,\"risk_amount\":%s}",
      AccountInfoInteger(ACCOUNT_LOGIN),
      JsonEscape(_Symbol),
      order_type,
      lot,
      DoubleToString(entry_price, _Digits),
      sl_json,
      tp_json,
      risk_percent_json,
      risk_amount_json
   );

   string body = "";
   int status = 0;
   if(!PostJsonToBackend("/api/rules/pre-trade-check", json, body, status))
   {
      reason = LastHttpError;
      if(reason == "")
         reason = "Pre-trade check HTTP failed.";
      return false;
   }

   if(!JsonHasKey(body, "allowed"))
   {
      reason = "Invalid pre-trade response: missing allowed field.";
      PrintFormat("AITradingCoach %s Body=%s", reason, body);
      return false;
   }

   bool allowed = JsonBoolValue(body, "allowed");
   string status_text = JsonStringValue(body, "status");
   string decision = JsonStringValue(body, "decision");
   string message = JsonStringValue(body, "message");
   reason = JsonStringValue(body, "reason");
   if(message != "")
      reason = message;
   if(reason == "")
      reason = allowed ? "Allowed" : "Blocked by backend.";
   PrintFormat(
      "AITradingCoach pre-trade response parsed: allowed=%s status=%s decision=%s reason=%s message=%s",
      allowed ? "true" : "false",
      status_text,
      decision,
      JsonStringValue(body, "reason"),
      message
   );
   return allowed;
}

bool RunPreCloseCheck(ulong ticket, string &reason)
{
   if(!PositionSelectByTicket(ticket))
   {
      reason = "Position not found.";
      return false;
   }

   string symbol = PositionGetString(POSITION_SYMBOL);
   long position_type_raw = PositionGetInteger(POSITION_TYPE);
   string position_type = (position_type_raw == POSITION_TYPE_BUY ? "BUY" : "SELL");
   double lot = PositionGetDouble(POSITION_VOLUME);
   double entry_price = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   double profit = PositionGetDouble(POSITION_PROFIT);
   double current_price = (position_type_raw == POSITION_TYPE_BUY ? SymbolInfoDouble(symbol, SYMBOL_BID) : SymbolInfoDouble(symbol, SYMBOL_ASK));
   double candle_close = iClose(symbol, PERIOD_CURRENT, 1);
   double ema34 = MovingAverageValue(symbol, PERIOD_CURRENT, 34, 1);
   double ema89 = MovingAverageValue(symbol, PERIOD_CURRENT, 89, 1);

   string json = StringFormat(
      "{\"account_number\":\"%I64d\",\"ticket\":\"%I64u\",\"symbol\":\"%s\",\"position_type\":\"%s\",\"lot\":%.2f,\"entry_price\":%s,\"current_price\":%s,\"profit\":%.2f,\"sl\":%s,\"tp\":%s,\"candle_close\":%s,\"ema34\":%s,\"ema89\":%s,\"close_reason\":\"close_all\"}",
      AccountInfoInteger(ACCOUNT_LOGIN),
      ticket,
      JsonEscape(symbol),
      position_type,
      lot,
      JsonNumberOrNull(entry_price, _Digits),
      JsonNumberOrNull(current_price, _Digits),
      profit,
      (sl > 0.0 ? DoubleToString(sl, _Digits) : "null"),
      (tp > 0.0 ? DoubleToString(tp, _Digits) : "null"),
      JsonNumberOrNull(candle_close, _Digits),
      JsonNumberOrNull(ema34, _Digits),
      JsonNumberOrNull(ema89, _Digits)
   );

   string body = "";
   int status = 0;
   if(!PostJsonToBackend("/api/rules/pre-close-check", json, body, status))
   {
      reason = LastHttpError;
      if(reason == "")
         reason = "Pre-close check HTTP failed.";
      return false;
   }

   bool allowed = JsonBoolValue(body, "allowed");
   string decision = JsonStringValue(body, "decision");
   string message = JsonStringValue(body, "message");
   reason = JsonStringValue(body, "reason");
   if(message != "")
      reason = message;
   if(reason == "")
      reason = allowed ? "Allowed" : "Blocked by backend.";

   if(allowed && decision == "WARN")
   {
      int choice = MessageBox(reason + "\n\nClose position anyway?", "AI Trading Coach close warning", MB_YESNO | MB_ICONWARNING);
      if(choice != IDYES)
      {
         reason = "Close cancelled after warning.";
         return false;
      }
   }

   return allowed;
}

string PlannedOrderKind(string order_type, double entry)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_size <= 0.0)
      tick_size = _Point;
   double tolerance = tick_size * 2.0;

   if(order_type == "BUY")
   {
      if(MathAbs(entry - ask) <= tolerance)
         return "BUY market";
      return entry > ask ? "BUY STOP" : "BUY LIMIT";
   }

   if(MathAbs(entry - bid) <= tolerance)
      return "SELL market";
   return entry < bid ? "SELL STOP" : "SELL LIMIT";
}

bool SendPlannedOrder(string order_type, double lot, double entry, double sl, double tp)
{
   string comment = "AI Trading Coach Panel";
   string kind = PlannedOrderKind(order_type, entry);
   Trade.SetExpertMagicNumber(MagicNumber);

   if(kind == "BUY market")
      return Trade.Buy(lot, _Symbol, 0.0, sl, tp, comment);
   if(kind == "SELL market")
      return Trade.Sell(lot, _Symbol, 0.0, sl, tp, comment);
   if(kind == "BUY LIMIT")
      return Trade.BuyLimit(lot, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   if(kind == "BUY STOP")
      return Trade.BuyStop(lot, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   if(kind == "SELL LIMIT")
      return Trade.SellLimit(lot, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, comment);
   if(kind == "SELL STOP")
      return Trade.SellStop(lot, entry, _Symbol, sl, tp, ORDER_TIME_GTC, 0, comment);

   return false;
}

void HandlePanelOrder(string order_type)
{
   ulong now_tick = GetTickCount();
   if(now_tick - LastClickTick < 500)
      return;
   LastClickTick = now_tick;

   PlanDirection = order_type;
   if(AutoTPEnabled)
   {
      UpdateTPFromRR(order_type);
      RefreshPlannerFromLines(false);
   }
   else
      RefreshPlannerFromLines();

   double entry_price = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   double tp = PriceLineValue(LINE_TP);
   double lot = UseRiskPositionSizing ? CalculateRiskLot(order_type, entry_price, sl) : NormalizeVolume(PanelDouble(OBJ_LOT));
   ObjectSetString(0, OBJ_LOT, OBJPROP_TEXT, DoubleToString(lot, 2));

   if(lot <= 0.0)
   {
      SetStatus("Blocked: lot must be greater than 0.", clrTomato);
      return;
   }

   string reason = "";
   if(!IsValidPlan(order_type, entry_price, sl, tp, reason))
   {
      SetStatus("Blocked: " + reason, clrTomato);
      return;
   }

   bool allowed = RunPreTradeCheck(order_type, lot, entry_price, sl, tp, reason);
   if(!allowed)
   {
      SetStatus("Blocked: " + TruncateText(reason, 420), clrTomato);
      return;
   }

   if(SafeMode)
   {
      string kind = PlannedOrderKind(order_type, entry_price);
      SetStatus("SafeMode simulation allowed: " + kind + " " + DoubleToString(lot, 2), clrGold);
      PrintFormat("AITradingCoach SafeMode=true. Simulated %s %.2f %s entry %.5f SL %.5f TP %.5f", kind, lot, _Symbol, entry_price, sl, tp);
      return;
   }

   bool sent = SendPlannedOrder(order_type, lot, entry_price, sl, tp);

   if(sent)
      SetStatus("Order sent: " + PlannedOrderKind(order_type, entry_price) + " " + DoubleToString(lot, 2), clrLime);
   else
      SetStatus("OrderSend failed: " + IntegerToString(GetLastError()) + " " + Trade.ResultRetcodeDescription(), clrTomato);
}

void HandleCloseAll()
{
   if(!AllowCloseAll)
   {
      SetStatus("Close All blocked. Set AllowCloseAll=true to enable.", clrGold);
      return;
   }
   if(SafeMode)
   {
      SetStatus("SafeMode simulation: Close All requested.", clrGold);
      return;
   }

   Trade.SetExpertMagicNumber(MagicNumber);
   int closed = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionSelectByTicket(ticket))
      {
         string reason = "";
         if(!RunPreCloseCheck(ticket, reason))
         {
            SetStatus("Close blocked: " + reason, clrTomato);
            PrintFormat("AITradingCoach close blocked for position %I64u: %s", ticket, reason);
            continue;
         }
         if(Trade.PositionClose(ticket))
            closed++;
         else
            PrintFormat("AITradingCoach failed closing position %I64u: %s", ticket, Trade.ResultRetcodeDescription());
      }
   }
   SetStatus("Close All completed. Closed positions: " + IntegerToString(closed), clrLime);
}

int OnInit()
{
   if(StringLen(BackendURL) < 8)
   {
      Print("AITradingCoach invalid BackendURL input.");
      return INIT_PARAMETERS_INCORRECT;
   }

   AutoTPEnabled = AutoTPByRR;
   DeleteTradePanel();
   CreateTradePanel();
   EventSetTimer(MathMax(1, SendIntervalSeconds));
   Print("AITradingCoach connector started. Remember to whitelist BackendURL in MT5 WebRequest settings.");
   SendHeartbeat();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteTradePanel();
   PrintFormat("AITradingCoach connector stopped. Reason=%d", reason);
}

void OnTimer()
{
   SendHeartbeat();
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_ORDER_ADD ||
      trans.type == TRADE_TRANSACTION_ORDER_UPDATE ||
      trans.type == TRADE_TRANSACTION_DEAL_ADD ||
      trans.type == TRADE_TRANSACTION_POSITION)
   {
      SendTradeEvent(trans, request);
   }
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_KEYDOWN)
   {
      if(IsOrderHotkey((int)lparam))
      {
         HandlePanelOrder(PlanDirection);
         ResetButtonStates();
      }
      return;
   }

   if(id == CHARTEVENT_OBJECT_DRAG)
   {
      if(sparam == LINE_ENTRY || sparam == LINE_SL)
      {
         if(AutoTPEnabled)
            ApplyAutoTPFromRR();
         else
            RefreshPlannerFromLines();
      }
      else if(sparam == LINE_TP)
         RefreshPlannerFromLines();
      return;
   }

   if(id == CHARTEVENT_OBJECT_ENDEDIT)
   {
      if(sparam == OBJ_ENTRY || sparam == OBJ_SL)
         RefreshLinesFromEdits(true);
      else if(sparam == OBJ_TP)
         RefreshLinesFromEdits(false);
      else if(sparam == OBJ_RR)
      {
         if(AutoTPEnabled)
         {
            SyncDirectionFromEntrySL();
            UpdateTPFromRR(PlanDirection);
            RefreshPlannerFromLines(false);
         }
         else
            RefreshPlannerFromLines();
      }
      else if(sparam == OBJ_RISK || sparam == OBJ_LOT)
         RefreshPlannerFromLines();
      return;
   }

   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   if(sparam == OBJ_BUY)
   {
      HandlePanelOrder("BUY");
      ResetButtonStates();
   }
   else if(sparam == OBJ_SELL)
   {
      HandlePanelOrder("SELL");
      ResetButtonStates();
   }
   else if(sparam == OBJ_CLOSE_ALL)
   {
      HandleCloseAll();
      ResetButtonStates();
   }
   else if(sparam == OBJ_AUTO_TP)
   {
      ToggleAutoTP();
      ResetButtonStates();
   }
}
