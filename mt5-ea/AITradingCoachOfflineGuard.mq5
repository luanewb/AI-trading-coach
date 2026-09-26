//+------------------------------------------------------------------+
//| AI Trading Coach Offline Guard                                  |
//| Standalone order panel with local risk and FTMO rule checks.      |
//+------------------------------------------------------------------+
#property strict
#property version   "1.002"
#property description "Standalone AI Trading Coach order panel. No backend or WebRequest required."
#property description "Risk, discipline, drawdown and FTMO news checks run locally in MT5."

#include <Trade/Trade.mqh>

input group "Order panel"
input bool SafeMode = true;
input bool AllowCloseAll = false;
input bool UseRiskPositionSizing = true;
input bool AutoTPByRR = true;
input double DefaultRiskPercent = 1.0;
input double DefaultRR = 2.0;
input string OrderHotkey = "t";
input ulong MagicNumber = 260830;

input group "Offline risk rules (backend-compatible defaults)"
input bool AllowTrading = true;
input int MaxTradesPerDay = 5;
input double MaxDailyLossPercent = 5.0;
input double MaxTotalLossPercent = 10.0;
input int MaxConsecutiveLosses = 3;
input int CooldownMinutesAfterLoss = 30;
input double MaxLot = 1.0;
input double MaxRiskPerTradePercent = 1.0;
input bool AutoPragueTradingDay = true;
input int TradingDayUtcOffsetHours = 2;

input group "Offline FTMO news rule"
input bool EnableNewsRestriction = true;
input int NewsMinutesBefore = 2;
input int NewsMinutesAfter = 2;
input bool NewsFailClosed = false;

CTrade Trade;

struct OfflineStats
{
   int trades_today;
   double daily_pnl;
   int consecutive_losses;
   double max_drawdown;
};

string PANEL_PREFIX = "ATCO_PANEL_";
string LINE_PREFIX = "ATCO_LINE_";
string OBJ_ENTRY = "ATCO_PANEL_ENTRY";
string OBJ_LOT = "ATCO_PANEL_LOT";
string OBJ_RISK = "ATCO_PANEL_RISK";
string OBJ_RR = "ATCO_PANEL_RR";
string OBJ_SL = "ATCO_PANEL_SL";
string OBJ_TP = "ATCO_PANEL_TP";
string OBJ_BUY = "ATCO_PANEL_BUY";
string OBJ_SELL = "ATCO_PANEL_SELL";
string OBJ_CLOSE_ALL = "ATCO_PANEL_CLOSE_ALL";
string OBJ_AUTO_TP = "ATCO_PANEL_AUTO_TP";
string OBJ_HOTKEY = "ATCO_PANEL_HOTKEY";
string OBJ_STATUS = "ATCO_PANEL_STATUS";
string OBJ_PLAN = "ATCO_PANEL_PLAN";
string LINE_ENTRY = "ATCO_LINE_ENTRY";
string LINE_SL = "ATCO_LINE_SL";
string LINE_TP = "ATCO_LINE_TP";
string PlanDirection = "BUY";
bool AutoTPEnabled = true;
ulong LastClickTick = 0;

string TruncateText(string value, int max_len)
{
   if(StringLen(value) <= max_len)
      return value;
   return StringSubstr(value, 0, max_len - 3) + "...";
}

int LastSundayOfMonth(int year, int month)
{
   MqlDateTime first_next_month;
   ZeroMemory(first_next_month);
   first_next_month.year = year;
   first_next_month.mon = month + 1;
   if(first_next_month.mon > 12)
   {
      first_next_month.mon = 1;
      first_next_month.year++;
   }
   first_next_month.day = 1;

   datetime last_day = StructToTime(first_next_month) - 86400;
   MqlDateTime parts;
   TimeToStruct(last_day, parts);
   return parts.day - parts.day_of_week;
}

int PragueUtcOffset(datetime gmt_now)
{
   MqlDateTime parts;
   TimeToStruct(gmt_now, parts);

   MqlDateTime start_parts;
   ZeroMemory(start_parts);
   start_parts.year = parts.year;
   start_parts.mon = 3;
   start_parts.day = LastSundayOfMonth(parts.year, 3);
   start_parts.hour = 1;

   MqlDateTime end_parts;
   ZeroMemory(end_parts);
   end_parts.year = parts.year;
   end_parts.mon = 10;
   end_parts.day = LastSundayOfMonth(parts.year, 10);
   end_parts.hour = 1;

   datetime dst_start_gmt = StructToTime(start_parts);
   datetime dst_end_gmt = StructToTime(end_parts);
   return (gmt_now >= dst_start_gmt && gmt_now < dst_end_gmt) ? 2 : 1;
}

datetime TradingDayStart()
{
   datetime server_now = TimeCurrent();
   datetime gmt_now = TimeGMT();
   long server_offset = (long)(server_now - gmt_now);
   int trading_day_offset = AutoPragueTradingDay ? PragueUtcOffset(gmt_now) : TradingDayUtcOffsetHours;
   long local_seconds = (long)gmt_now + (long)trading_day_offset * 3600;
   long local_midnight = (local_seconds / 86400) * 86400;
   long start_gmt = local_midnight - (long)trading_day_offset * 3600;
   return (datetime)(start_gmt + server_offset);
}

bool IsTradingDeal(ulong deal_ticket)
{
   long deal_type = HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
   return deal_type == DEAL_TYPE_BUY || deal_type == DEAL_TYPE_SELL;
}

bool IsEntryDeal(ulong deal_ticket)
{
   long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
   return entry == DEAL_ENTRY_IN || entry == DEAL_ENTRY_INOUT;
}

bool IsExitDeal(ulong deal_ticket)
{
   long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
   return entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY || entry == DEAL_ENTRY_INOUT;
}

double DealNetPnl(ulong deal_ticket)
{
   return HistoryDealGetDouble(deal_ticket, DEAL_PROFIT)
      + HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION)
      + HistoryDealGetDouble(deal_ticket, DEAL_SWAP)
      + HistoryDealGetDouble(deal_ticket, DEAL_FEE);
}

bool ContainsPositionId(const ulong &items[], int count, ulong value)
{
   for(int i = 0; i < count; i++)
   {
      if(items[i] == value)
         return true;
   }
   return false;
}

bool CalculateOfflineStats(OfflineStats &stats, string &error)
{
   stats.trades_today = 0;
   stats.daily_pnl = 0.0;
   stats.consecutive_losses = 0;
   stats.max_drawdown = 0.0;
   error = "";

   datetime now = TimeCurrent();
   if(!HistorySelect(0, now))
   {
      error = "Cannot read MT5 trade history. Error " + IntegerToString(GetLastError()) + ".";
      return false;
   }

   datetime day_start = TradingDayStart();
   ulong positions_today[];
   int unique_positions = 0;
   double equity_curve = 0.0;
   double equity_peak = 0.0;
   int total = HistoryDealsTotal();

   for(int i = 0; i < total; i++)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0 || !IsTradingDeal(deal_ticket))
         continue;

      datetime deal_time = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
      if(deal_time >= day_start && IsEntryDeal(deal_ticket))
      {
         ulong position_id = (ulong)HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
         if(position_id == 0)
            position_id = deal_ticket;
         if(!ContainsPositionId(positions_today, unique_positions, position_id))
         {
            ArrayResize(positions_today, unique_positions + 1);
            positions_today[unique_positions] = position_id;
            unique_positions++;
         }
      }

      if(IsExitDeal(deal_ticket))
      {
         double net_pnl = DealNetPnl(deal_ticket);
         equity_curve += net_pnl;
         if(equity_curve > equity_peak)
            equity_peak = equity_curve;
         double drawdown = equity_peak - equity_curve;
         if(drawdown > stats.max_drawdown)
            stats.max_drawdown = drawdown;
         if(deal_time >= day_start)
            stats.daily_pnl += net_pnl;
      }
   }

   stats.trades_today = unique_positions;

   for(int i = total - 1; i >= 0; i--)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0 || !IsTradingDeal(deal_ticket) || !IsExitDeal(deal_ticket))
         continue;
      datetime deal_time = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
      if(deal_time < day_start)
         break;
      if(DealNetPnl(deal_ticket) < 0.0)
         stats.consecutive_losses++;
      else
         break;
   }

   return true;
}

bool LatestClosedTradeIsLoss(datetime &closed_at, string &symbol, double &lot, double &net_pnl)
{
   closed_at = 0;
   symbol = "";
   lot = 0.0;
   net_pnl = 0.0;

   if(!HistorySelect(0, TimeCurrent()))
      return false;

   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0 || !IsTradingDeal(deal_ticket) || !IsExitDeal(deal_ticket))
         continue;

      net_pnl = DealNetPnl(deal_ticket);
      if(net_pnl >= 0.0)
         return false;

      closed_at = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
      symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
      lot = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
      return true;
   }
   return false;
}

string CleanUpperSymbol(string symbol)
{
   StringToUpper(symbol);
   string clean = "";
   for(int i = 0; i < StringLen(symbol); i++)
   {
      ushort ch = StringGetCharacter(symbol, i);
      if((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9'))
         clean += ShortToString(ch);
   }
   return clean;
}

bool IsUsdSensitiveSymbol(string symbol)
{
   string clean = CleanUpperSymbol(symbol);
   string prefixes[] = {"EURUSD","GBPUSD","AUDUSD","NZDUSD","USDJPY","USDCHF","USDCAD","XAUUSD","XAGUSD",
                        "US30","DJ30","DJI","NAS100","US100","USTEC","SPX500","US500","USOIL","WTI"};
   for(int i = 0; i < ArraySize(prefixes); i++)
   {
      if(StringFind(clean, prefixes[i]) == 0)
         return true;
   }
   int scan_length = MathMin(8, StringLen(clean));
   return StringFind(StringSubstr(clean, 0, scan_length), "USD") >= 0;
}

bool IsRestrictedUsdEventName(string name)
{
   StringToLower(name);
   string aliases[] = {
      "non farm payroll", "nonfarm payroll", "non-farm employment change",
      "unemployment rate", "jobless rate",
      "average hourly earnings", "wage", "wages", "earnings m/m",
      "consumer price index", "cpi", "core cpi", "inflation rate",
      "advance gdp", "gross domestic product advance", "gdp advance",
      "fomc rate decision", "federal funds rate", "interest rate decision", "fed interest rate",
      "fomc statement", "fed monetary policy statement",
      "fomc press conference", "fed press conference", "fomc presser",
      "fomc minutes", "fomc meeting minutes", "fed minutes"
   };
   for(int i = 0; i < ArraySize(aliases); i++)
   {
      if(StringFind(name, aliases[i]) >= 0)
         return true;
   }
   return false;
}

bool CheckOfflineNewsRestriction(string symbol, string action, string &reason)
{
   if(!EnableNewsRestriction || !IsUsdSensitiveSymbol(symbol))
      return true;

   datetime now = TimeTradeServer();
   if(now <= 0)
      now = TimeCurrent();
   datetime from_time = now - MathMax(0, NewsMinutesAfter) * 60;
   datetime to_time = now + MathMax(0, NewsMinutesBefore) * 60;
   MqlCalendarValue values[];
   ResetLastError();
   int count = CalendarValueHistory(values, from_time, to_time, NULL, "USD");
   if(count < 0)
   {
      int calendar_error = GetLastError();
      PrintFormat("AITradingCoachOffline calendar unavailable. Error=%d", calendar_error);
      if(NewsFailClosed)
      {
         reason = "NEWS_RESTRICTED_WINDOW: calendar unavailable (fail-closed).";
         return false;
      }
      return true;
   }

   for(int i = 0; i < count; i++)
   {
      MqlCalendarEvent event;
      if(!CalendarEventById(values[i].event_id, event))
         continue;
      if(!IsRestrictedUsdEventName(event.name))
         continue;

      datetime event_time = values[i].time;
      datetime window_start = event_time - MathMax(0, NewsMinutesBefore) * 60;
      datetime window_end = event_time + MathMax(0, NewsMinutesAfter) * 60;
      if(now >= window_start && now <= window_end)
      {
         reason = StringFormat(
            "NEWS_RESTRICTED_WINDOW: %s blocks %s until %s.",
            event.name,
            action,
            TimeToString(window_end, TIME_DATE | TIME_MINUTES)
         );
         return false;
      }
   }
   return true;
}

bool ValidateOfflineInputs(string &reason)
{
   if(MaxTradesPerDay < 1 || MaxTradesPerDay > 100)
      reason = "MaxTradesPerDay must be from 1 to 100.";
   else if(MaxDailyLossPercent < 0.0 || MaxDailyLossPercent > 100.0)
      reason = "MaxDailyLossPercent must be from 0 to 100.";
   else if(MaxTotalLossPercent < 0.0 || MaxTotalLossPercent > 100.0)
      reason = "MaxTotalLossPercent must be from 0 to 100.";
   else if(MaxConsecutiveLosses < 1 || MaxConsecutiveLosses > 100)
      reason = "MaxConsecutiveLosses must be from 1 to 100.";
   else if(CooldownMinutesAfterLoss < 0 || CooldownMinutesAfterLoss > 1440)
      reason = "CooldownMinutesAfterLoss must be from 0 to 1440.";
   else if(MaxLot < 0.0)
      reason = "MaxLot cannot be negative.";
   else if(MaxRiskPerTradePercent < 0.0 || MaxRiskPerTradePercent > 100.0)
      reason = "MaxRiskPerTradePercent must be from 0 to 100.";
   else if(NewsMinutesBefore < 0 || NewsMinutesAfter < 0)
      reason = "News window minutes cannot be negative.";
   else if(!AutoPragueTradingDay && (TradingDayUtcOffsetHours < -12 || TradingDayUtcOffsetHours > 14))
      reason = "TradingDayUtcOffsetHours must be from -12 to 14.";
   else
      return true;
   return false;
}

void SetStatus(string message, color text_color = clrWhite)
{
   ObjectSetString(0, OBJ_STATUS, OBJPROP_TEXT, "Risk Status: " + message);
   ObjectSetInteger(0, OBJ_STATUS, OBJPROP_COLOR, text_color);
   Print("AITradingCoachOffline status: " + message);
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

ulong SymbolHash(string s)
{
   ulong hash = 5381;
   for(int i = 0; i < StringLen(s); i++)
      hash = ((hash << 5) + hash) + (uchar)StringGetCharacter(s, i);
   return hash;
}

string GVKey(string key_name)
{
   return StringFormat("ATCO_%I64d_%s", ChartID(), key_name);
}

void SaveStateToGlobal()
{
   double entry = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   double tp = PriceLineValue(LINE_TP);
   bool tp_exists = (ObjectFind(0, LINE_TP) >= 0 && tp > 0.0);

   if(entry > 0.0)
      GlobalVariableSet(GVKey("ENTRY"), entry);
   if(sl > 0.0)
      GlobalVariableSet(GVKey("SL"), sl);

   if(tp_exists)
   {
      GlobalVariableSet(GVKey("TP"), tp);
      GlobalVariableSet(GVKey("TP_EXISTS"), 1.0);
   }
   else
   {
      GlobalVariableSet(GVKey("TP"), 0.0);
      GlobalVariableSet(GVKey("TP_EXISTS"), 0.0);
   }

   GlobalVariableSet(GVKey("SYM_HASH"), (double)SymbolHash(_Symbol));
   GlobalVariableSet(GVKey("AUTOTP"), AutoTPEnabled ? 1.0 : 0.0);
   GlobalVariableSet(GVKey("DIRECTION"), (PlanDirection == "SELL") ? -1.0 : 1.0);

   double risk = StringToDouble(ObjectGetString(0, OBJ_RISK, OBJPROP_TEXT));
   if(risk > 0.0)
      GlobalVariableSet(GVKey("RISK"), risk);

   double rr = StringToDouble(ObjectGetString(0, OBJ_RR, OBJPROP_TEXT));
   if(rr > 0.0)
      GlobalVariableSet(GVKey("RR"), rr);

   double lot = StringToDouble(ObjectGetString(0, OBJ_LOT, OBJPROP_TEXT));
   if(lot > 0.0)
      GlobalVariableSet(GVKey("LOT"), lot);
}

void ClearGlobalState()
{
   GlobalVariableDel(GVKey("ENTRY"));
   GlobalVariableDel(GVKey("SL"));
   GlobalVariableDel(GVKey("TP"));
   GlobalVariableDel(GVKey("TP_EXISTS"));
   GlobalVariableDel(GVKey("SYM_HASH"));
   GlobalVariableDel(GVKey("RISK"));
   GlobalVariableDel(GVKey("RR"));
   GlobalVariableDel(GVKey("LOT"));
   GlobalVariableDel(GVKey("AUTOTP"));
   GlobalVariableDel(GVKey("DIRECTION"));
}

void CreatePriceLine(string name, string text, double price, color line_color)
{
   if(ObjectFind(0, name) >= 0)
   {
      ObjectSetInteger(0, name, OBJPROP_COLOR, line_color);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTED, true);
      ObjectSetString(0, name, OBJPROP_TEXT, text);
      return;
   }
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
   if(value <= 0.0)
      ObjectSetString(0, object_name, OBJPROP_TEXT, "0");
   else
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
      PrintFormat("AITradingCoachOffline OrderCalcProfit failed: %d", GetLastError());
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
      PrintFormat("AITradingCoachOffline OrderCalcProfit risk amount failed: %d", GetLastError());
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
   {
      if(GlobalVariableCheck(GVKey("RR")))
         rr = GlobalVariableGet(GVKey("RR"));
      if(rr <= 0.0)
         rr = DefaultRR;
      ObjectSetString(0, OBJ_RR, OBJPROP_TEXT, DoubleToString(rr, 2));
   }

   double entry = PriceLineValue(LINE_ENTRY);
   double sl = PriceLineValue(LINE_SL);
   double risk = MathAbs(entry - sl);
   if(entry <= 0.0 || sl <= 0.0 || risk <= 0.0)
      return;

   double tp = (order_type == "BUY" ? entry + risk * rr : entry - risk * rr);
   tp = NormalizePrice(tp);
   if(ObjectFind(0, LINE_TP) < 0)
      CreatePriceLine(LINE_TP, "ATC Offline Take Profit", tp, clrLimeGreen);
   else
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
   {
      string rr_text = (tp > 0.0) ? ("RR " + ObjectGetString(0, OBJ_RR, OBJPROP_TEXT)) : "No TP";
      ObjectSetString(0, OBJ_PLAN, OBJPROP_TEXT, StringFormat("Plan: %s | %s | Risk %s%% | Lot %.2f", PlanDirection, rr_text, ObjectGetString(0, OBJ_RISK, OBJPROP_TEXT), lot));
   }
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
   {
      if(ObjectFind(0, LINE_TP) < 0)
         CreatePriceLine(LINE_TP, "ATC Offline Take Profit", tp, clrLimeGreen);
      else
         ObjectSetDouble(0, LINE_TP, OBJPROP_PRICE, tp);
   }
   else
   {
      ObjectDelete(0, LINE_TP);
   }

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
   if(AutoTPEnabled)
   {
      double rr = StringToDouble(ObjectGetString(0, OBJ_RR, OBJPROP_TEXT));
      if(rr <= 0.0 && GlobalVariableCheck(GVKey("RR")))
      {
         double saved_rr = GlobalVariableGet(GVKey("RR"));
         if(saved_rr > 0.0)
            ObjectSetString(0, OBJ_RR, OBJPROP_TEXT, DoubleToString(saved_rr, 2));
      }
      ApplyAutoTPFromRR();
   }
   RefreshPlannerFromLines(false);
}

void CreateTradeLines()
{
   bool symbol_changed = false;
   if(GlobalVariableCheck(GVKey("SYM_HASH")))
   {
      if((ulong)GlobalVariableGet(GVKey("SYM_HASH")) != SymbolHash(_Symbol))
         symbol_changed = true;
   }

   double entry = 0.0;
   double sl = 0.0;
   double tp = 0.0;
   bool tp_exists = true;

   if(!symbol_changed)
   {
      entry = PriceLineValue(LINE_ENTRY);
      sl    = PriceLineValue(LINE_SL);
      tp    = PriceLineValue(LINE_TP);

      if(entry <= 0.0 && GlobalVariableCheck(GVKey("ENTRY")))
         entry = NormalizePrice(GlobalVariableGet(GVKey("ENTRY")));
      if(sl <= 0.0 && GlobalVariableCheck(GVKey("SL")))
         sl = NormalizePrice(GlobalVariableGet(GVKey("SL")));
      if(tp <= 0.0 && GlobalVariableCheck(GVKey("TP")))
         tp = NormalizePrice(GlobalVariableGet(GVKey("TP")));

      if(GlobalVariableCheck(GVKey("TP_EXISTS")))
         tp_exists = (GlobalVariableGet(GVKey("TP_EXISTS")) > 0.5);
      else
         tp_exists = (tp > 0.0 || ObjectFind(0, LINE_TP) >= 0);
   }
   else
   {
      ObjectsDeleteAll(0, LINE_PREFIX);
      ClearGlobalState();
      tp_exists = true;
   }

   if(entry <= 0.0)
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      entry = NormalizePrice((bid + ask) / 2.0);
      if(entry <= 0.0)
         entry = NormalizePrice(iClose(_Symbol, PERIOD_CURRENT, 0));
   }

   double default_distance = MathMax(100.0 * _Point, SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE) * 100.0);
   if(sl <= 0.0)
      sl = NormalizePrice(entry - default_distance);

   CreatePriceLine(LINE_ENTRY, "ATC Offline Entry", entry, clrDodgerBlue);
   CreatePriceLine(LINE_SL, "ATC Offline Stop Loss", sl, clrTomato);

   if(AutoTPEnabled || (tp_exists && tp > 0.0))
   {
      if(tp <= 0.0)
         tp = NormalizePrice(entry + default_distance * DefaultRR);
      CreatePriceLine(LINE_TP, "ATC Offline Take Profit", tp, clrLimeGreen);
   }
   else
   {
      ObjectDelete(0, LINE_TP);
      tp = 0.0;
   }

   SaveStateToGlobal();
}

void CreateTradePanel()
{
   double risk_val = DefaultRiskPercent;
   if(GlobalVariableCheck(GVKey("RISK")))
      risk_val = GlobalVariableGet(GVKey("RISK"));

   double rr_val = DefaultRR;
   if(GlobalVariableCheck(GVKey("RR")))
      rr_val = GlobalVariableGet(GVKey("RR"));

   double lot_val = 0.10;
   if(GlobalVariableCheck(GVKey("LOT")))
      lot_val = GlobalVariableGet(GVKey("LOT"));

   CreatePanelLabel(PANEL_PREFIX + "TITLE", SafeMode ? "ATC Offline Guard (SAFE)" : "ATC Offline Guard (LIVE)", 12, 18, 260, SafeMode ? clrGold : clrLime);
   CreatePanelLabel(PANEL_PREFIX + "ENTRY_LABEL", "Entry", 12, 45, 40);
   CreatePanelEdit(OBJ_ENTRY, "0", 58, 42, 92);
   CreatePanelLabel(PANEL_PREFIX + "SL_LABEL", "SL", 160, 45, 25);
   CreatePanelEdit(OBJ_SL, "0", 190, 42, 92);
   CreatePanelLabel(PANEL_PREFIX + "TP_LABEL", "TP", 292, 45, 25);
   CreatePanelEdit(OBJ_TP, "0", 322, 42, 92);
   CreatePanelLabel(PANEL_PREFIX + "RISK_LABEL", "Risk %", 12, 74, 50);
   CreatePanelEdit(OBJ_RISK, DoubleToString(risk_val, 2), 70, 71, 58);
   CreatePanelLabel(PANEL_PREFIX + "RR_LABEL", "RR", 138, 74, 25);
   CreatePanelEdit(OBJ_RR, DoubleToString(rr_val, 2), 166, 71, 58);
   CreatePanelLabel(PANEL_PREFIX + "LOT_LABEL", "Lot", 234, 74, 30);
   CreatePanelEdit(OBJ_LOT, DoubleToString(lot_val, 2), 266, 71, 58);
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

void DeleteTradePanel(bool delete_lines = false)
{
   ObjectsDeleteAll(0, PANEL_PREFIX);
   if(delete_lines)
      ObjectsDeleteAll(0, LINE_PREFIX);
}

double PanelDouble(string object_name)
{
   return StringToDouble(ObjectGetString(0, object_name, OBJPROP_TEXT));
}

bool RunPreTradeCheck(string order_type, double lot, double entry_price, double sl, double tp, string &reason)
{
   reason = "Allowed by offline rules.";

   if(!AllowTrading)
   {
      reason = "PLATFORM_TRADING_ALLOWED: trading is disabled in EA inputs.";
      return false;
   }

   OfflineStats stats;
   string stats_error = "";
   if(!CalculateOfflineStats(stats, stats_error))
   {
      reason = "RULE_ENGINE_ERROR: " + stats_error;
      return false;
   }

   if(stats.trades_today >= MaxTradesPerDay)
   {
      reason = StringFormat("MAX_TRADES_PER_DAY: trades today reached %d / %d.", stats.trades_today, MaxTradesPerDay);
      return false;
   }

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double base_equity = equity - stats.daily_pnl;
   double daily_loss_percent = (base_equity > 0.0 && stats.daily_pnl < 0.0)
      ? MathAbs(stats.daily_pnl) / base_equity * 100.0
      : 0.0;
   if(MaxDailyLossPercent > 0.0 && daily_loss_percent >= MaxDailyLossPercent)
   {
      reason = StringFormat("MAX_DAILY_LOSS: daily equity loss %.2f%% reached max %.2f%%.", daily_loss_percent, MaxDailyLossPercent);
      return false;
   }

   double total_loss_percent = (balance > 0.0 && equity < balance) ? (balance - equity) / balance * 100.0 : 0.0;
   if(MaxTotalLossPercent > 0.0 && total_loss_percent >= MaxTotalLossPercent)
   {
      reason = StringFormat("MAX_TOTAL_LOSS: total equity loss %.2f%% reached max %.2f%%.", total_loss_percent, MaxTotalLossPercent);
      return false;
   }

   double drawdown_percent = (balance > 0.0 && stats.max_drawdown > 0.0) ? stats.max_drawdown / balance * 100.0 : 0.0;
   if(MaxTotalLossPercent > 0.0 && drawdown_percent >= MaxTotalLossPercent)
   {
      reason = StringFormat("MAX_DRAWDOWN_LIMIT: realized drawdown %.2f%% reached max %.2f%%.", drawdown_percent, MaxTotalLossPercent);
      return false;
   }

   if(stats.consecutive_losses >= MaxConsecutiveLosses)
   {
      reason = StringFormat("MAX_CONSECUTIVE_LOSSES: reached %d / %d.", stats.consecutive_losses, MaxConsecutiveLosses);
      return false;
   }

   datetime last_loss_time;
   string last_loss_symbol;
   double last_loss_lot;
   double last_loss_pnl;
   bool latest_was_loss = LatestClosedTradeIsLoss(last_loss_time, last_loss_symbol, last_loss_lot, last_loss_pnl);
   datetime cooldown_until = last_loss_time + MathMax(0, CooldownMinutesAfterLoss) * 60;
   if(latest_was_loss && CooldownMinutesAfterLoss > 0 && cooldown_until > TimeCurrent())
   {
      bool same_symbol = (last_loss_symbol == _Symbol);
      bool larger_lot = (lot > last_loss_lot);
      string revenge = (same_symbol || larger_lot) ? " REVENGE_TRADING pattern detected." : "";
      reason = StringFormat("COOLDOWN_AFTER_LOSS: blocked until %s.%s", TimeToString(cooldown_until, TIME_DATE | TIME_MINUTES), revenge);
      return false;
   }

   if(sl <= 0.0)
   {
      reason = "NO_STOP_LOSS: every new trade requires a stop loss.";
      return false;
   }

   if(lot > MaxLot)
   {
      reason = StringFormat("MAX_LOT_SIZE: lot %.2f exceeds max %.2f.", lot, MaxLot);
      return false;
   }

   double risk_amount = CalculateRiskAmount(order_type, lot, entry_price, sl);
   double risk_percent = (equity > 0.0 && risk_amount > 0.0) ? risk_amount / equity * 100.0 : 0.0;
   if(MaxRiskPerTradePercent > 0.0 && risk_percent > MaxRiskPerTradePercent)
   {
      reason = StringFormat("RISK_PER_TRADE: planned risk %.2f%% exceeds max %.2f%%.", risk_percent, MaxRiskPerTradePercent);
      return false;
   }

   if(!CheckOfflineNewsRestriction(_Symbol, "new_order", reason))
      return false;

   double warning_threshold = MaxDailyLossPercent * 0.80;
   if(MaxDailyLossPercent > 0.0 && daily_loss_percent >= warning_threshold)
      PrintFormat("AITradingCoachOffline MAX_DAILY_LOSS_WARNING: %.2f%% is near max %.2f%%.", daily_loss_percent, MaxDailyLossPercent);

   return true;
}

bool RunPreCloseCheck(ulong ticket, string &reason)
{
   if(!PositionSelectByTicket(ticket))
   {
      reason = "Position not found.";
      return false;
   }

   string symbol = PositionGetString(POSITION_SYMBOL);
   return CheckOfflineNewsRestriction(symbol, "manual_close", reason);
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
   string comment = "ATC Offline Guard";
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
      PrintFormat("AITradingCoachOffline SafeMode=true. Simulated %s %.2f %s entry %.5f SL %.5f TP %.5f", kind, lot, _Symbol, entry_price, sl, tp);
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
            PrintFormat("AITradingCoachOffline close blocked for position %I64u: %s", ticket, reason);
            continue;
         }
         if(Trade.PositionClose(ticket))
            closed++;
         else
            PrintFormat("AITradingCoachOffline failed closing position %I64u: %s", ticket, Trade.ResultRetcodeDescription());
      }
   }
   SetStatus("Close All completed. Closed positions: " + IntegerToString(closed), clrLime);
}

int OnInit()
{
   string input_error = "";
   if(!ValidateOfflineInputs(input_error))
   {
      Print("AITradingCoachOffline invalid input: " + input_error);
      return INIT_PARAMETERS_INCORRECT;
   }

   AutoTPEnabled = AutoTPByRR;
   if(GlobalVariableCheck(GVKey("AUTOTP")))
      AutoTPEnabled = (GlobalVariableGet(GVKey("AUTOTP")) > 0.5);
   if(GlobalVariableCheck(GVKey("DIRECTION")))
      PlanDirection = (GlobalVariableGet(GVKey("DIRECTION")) < 0.0) ? "SELL" : "BUY";

   DeleteTradePanel(false);
   CreateTradePanel();
   Print("AITradingCoachOffline Guard started. All checks run locally; no backend or WebRequest is used.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   SaveStateToGlobal();
   if(reason == REASON_REMOVE || reason == REASON_CHARTCLOSE)
   {
      DeleteTradePanel(true);
      ClearGlobalState();
   }
   else
   {
      DeleteTradePanel(false);
   }
   PrintFormat("AITradingCoachOffline Guard stopped. Reason=%d", reason);
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_DELETE)
   {
      if(sparam == LINE_TP)
      {
         if(AutoTPEnabled)
         {
            AutoTPEnabled = false;
            UpdateAutoTPButton();
         }
         SetEditText(OBJ_TP, 0.0);
         RefreshPlannerFromLines(false);
         SaveStateToGlobal();
      }
      return;
   }

   if(id == CHARTEVENT_KEYDOWN)
   {
      if(IsOrderHotkey((int)lparam))
      {
         HandlePanelOrder(PlanDirection);
         ResetButtonStates();
         SaveStateToGlobal();
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
         SaveStateToGlobal();
      }
      else if(sparam == LINE_TP)
      {
         RefreshPlannerFromLines();
         SaveStateToGlobal();
      }
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

      SaveStateToGlobal();
      return;
   }

   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   if(sparam == OBJ_BUY)
   {
      HandlePanelOrder("BUY");
      ResetButtonStates();
      SaveStateToGlobal();
   }
   else if(sparam == OBJ_SELL)
   {
      HandlePanelOrder("SELL");
      ResetButtonStates();
      SaveStateToGlobal();
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
      SaveStateToGlobal();
   }
}
