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
input ulong MagicNumber = 260629;

CTrade Trade;

string PANEL_PREFIX = "ATC_PANEL_";
string OBJ_LOT = "ATC_PANEL_LOT";
string OBJ_SL = "ATC_PANEL_SL";
string OBJ_TP = "ATC_PANEL_TP";
string OBJ_BUY = "ATC_PANEL_BUY";
string OBJ_SELL = "ATC_PANEL_SELL";
string OBJ_CLOSE_ALL = "ATC_PANEL_CLOSE_ALL";
string OBJ_STATUS = "ATC_PANEL_STATUS";
string LastHttpError = "";

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

bool PostJsonToBackend(string endpoint, string json, string &body, int &http_status)
{
   LastHttpError = "";
   string url = NormalizeBaseUrl(BackendURL) + endpoint;
   if(PostJsonToUrl(url, endpoint, json, body, http_status))
      return true;

   string first_error = LastHttpError;
   string alternate_base = AlternateLocalBaseUrl(BackendURL);
   if(alternate_base != "")
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
   PrintFormat("AITradingCoach POST %s payload=%s", url, json);
   http_status = WebRequest("POST", url, headers, 10000, post, result, result_headers);
   if(http_status == -1)
   {
      int err = GetLastError();
      LastHttpError = StringFormat("WebRequest error %d. Check MT5 WebRequest whitelist for %s.", err, BackendURL);
      PrintFormat("AITradingCoach %s", LastHttpError);
      return false;
   }

   body = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   if(http_status < 200 || http_status >= 300)
   {
      LastHttpError = StringFormat("HTTP %d from %s: %s headers=%s", http_status, endpoint, body, result_headers);
      PrintFormat("AITradingCoach %s", LastHttpError);
      return false;
   }

   PrintFormat("AITradingCoach sent %s successfully. HTTP %d", endpoint, http_status);
   return true;
}

string JsonStringValue(string json, string key)
{
   string marker = "\"" + key + "\":\"";
   int start = StringFind(json, marker);
   if(start < 0)
      return "";
   start += StringLen(marker);
   int end = StringFind(json, "\"", start);
   if(end < 0)
      return "";
   string value = StringSubstr(json, start, end - start);
   StringReplace(value, "\\\"", "\"");
   StringReplace(value, "\\n", "\n");
   return value;
}

bool JsonBoolValue(string json, string key)
{
   string marker = "\"" + key + "\":";
   int start = StringFind(json, marker);
   if(start < 0)
      return false;
   start += StringLen(marker);
   string value = StringSubstr(json, start, 5);
   return StringFind(value, "true") == 0;
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

void CreateTradePanel()
{
   CreatePanelLabel(PANEL_PREFIX + "TITLE", SafeMode ? "AI Trading Coach Panel (SAFE)" : "AI Trading Coach Panel (LIVE)", 12, 18, 260, SafeMode ? clrGold : clrLime);
   CreatePanelLabel(PANEL_PREFIX + "LOT_LABEL", "Lot", 12, 45, 40);
   CreatePanelEdit(OBJ_LOT, "0.10", 52, 42, 70);
   CreatePanelLabel(PANEL_PREFIX + "SL_LABEL", "SL", 132, 45, 30);
   CreatePanelEdit(OBJ_SL, "0", 162, 42, 86);
   CreatePanelLabel(PANEL_PREFIX + "TP_LABEL", "TP", 258, 45, 30);
   CreatePanelEdit(OBJ_TP, "0", 288, 42, 86);
   CreatePanelButton(OBJ_BUY, "BUY", 12, 74, 78, clrSeaGreen);
   CreatePanelButton(OBJ_SELL, "SELL", 98, 74, 78, clrFireBrick);
   CreatePanelButton(OBJ_CLOSE_ALL, "CLOSE ALL", 184, 74, 100, clrDimGray);
   CreatePanelLabel(OBJ_STATUS, "Risk Status: waiting", 12, 108, 380, clrWhite);
   ChartRedraw();
}

void DeleteTradePanel()
{
   ObjectsDeleteAll(0, PANEL_PREFIX);
}

double PanelDouble(string object_name)
{
   return StringToDouble(ObjectGetString(0, object_name, OBJPROP_TEXT));
}

bool RunPreTradeCheck(string order_type, double lot, double entry_price, double sl, double tp, string &reason)
{
   string sl_json = (sl > 0.0 ? DoubleToString(sl, _Digits) : "null");
   string tp_json = (tp > 0.0 ? DoubleToString(tp, _Digits) : "null");
   string json = StringFormat(
      "{\"account_number\":\"%I64d\",\"symbol\":\"%s\",\"order_type\":\"%s\",\"lot\":%.2f,\"entry_price\":%s,\"sl\":%s,\"tp\":%s}",
      AccountInfoInteger(ACCOUNT_LOGIN),
      JsonEscape(_Symbol),
      order_type,
      lot,
      DoubleToString(entry_price, _Digits),
      sl_json,
      tp_json
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

   bool allowed = JsonBoolValue(body, "allowed");
   reason = JsonStringValue(body, "reason");
   if(reason == "")
      reason = allowed ? "Allowed" : "Blocked by backend.";
   return allowed;
}

void HandlePanelOrder(string order_type)
{
   double lot = PanelDouble(OBJ_LOT);
   double sl = PanelDouble(OBJ_SL);
   double tp = PanelDouble(OBJ_TP);
   double entry_price = (order_type == "BUY" ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID));

   if(lot <= 0.0)
   {
      SetStatus("Blocked: lot must be greater than 0.", clrTomato);
      return;
   }
   if(entry_price <= 0.0)
   {
      SetStatus("Blocked: no market price available.", clrTomato);
      return;
   }

   string reason = "";
   bool allowed = RunPreTradeCheck(order_type, lot, entry_price, sl, tp, reason);
   if(!allowed)
   {
      SetStatus("Blocked: " + reason, clrTomato);
      return;
   }

   if(SafeMode)
   {
      SetStatus("SafeMode simulation allowed: " + order_type + " " + DoubleToString(lot, 2), clrGold);
      PrintFormat("AITradingCoach SafeMode=true. Simulated %s %.2f %s at %.5f SL %.5f TP %.5f", order_type, lot, _Symbol, entry_price, sl, tp);
      return;
   }

   Trade.SetExpertMagicNumber(MagicNumber);
   bool sent = false;
   if(order_type == "BUY")
      sent = Trade.Buy(lot, _Symbol, 0.0, sl, tp, "AI Trading Coach Panel");
   else
      sent = Trade.Sell(lot, _Symbol, 0.0, sl, tp, "AI Trading Coach Panel");

   if(sent)
      SetStatus("Order sent: " + order_type + " " + DoubleToString(lot, 2), clrLime);
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
   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   if(sparam == OBJ_BUY)
      HandlePanelOrder("BUY");
   else if(sparam == OBJ_SELL)
      HandlePanelOrder("SELL");
   else if(sparam == OBJ_CLOSE_ALL)
      HandleCloseAll();
}
