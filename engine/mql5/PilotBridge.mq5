#property version   "1.00"
#property description "AlgoRE PilotBridge / Chart Manager — telemetry only, never trades"
input string InpApiBase = "https://YOUR-API-HOST/api/v1";
input string InpPilotToken = "<pilot JWT>";
input int    InpHeartbeatSeconds = 30;

int OnInit()
{
   EventSetTimer(InpHeartbeatSeconds);
   SendEnvelope("attach", "");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   SendEnvelope("heartbeat", "");
}

// Fires for every deal on the account, including other bots' magic numbers.
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &req, const MqlTradeResult &res)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!IsClosingDeal(trans.deal)) return;
   SendTrade(trans.deal);
}

bool IsClosingDeal(ulong deal_ticket)
{
   if(!HistorySelectByPosition(0)) { HistorySelect(0, TimeCurrent()); }
   if(!HistoryDealSelect(deal_ticket)) return(false);
   long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
   return(entry == DEAL_ENTRY_OUT);
}

string Esc(string s)
{
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   StringReplace(out, "\r", " ");
   StringReplace(out, "\n", " ");
   return(out);
}

string Envelope(const string type, const string extra)
{
   string s = "";
   s += "{\"v\":1,\"type\":\"" + type + "\"";
   s += ",\"sent_at\":\"" + TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "Z\"";
   s += ",\"pilot_id\":\"" + Esc(IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))) + "-MT5\"";
   s += ",\"account\":{\"login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   s += ",\"server\":\"" + Esc(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   s += ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2);
   s += ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2);
   s += ",\"currency\":\"" + Esc(AccountInfoString(ACCOUNT_CURRENCY)) + "\"}";
   s += ",\"chart\":{\"symbol\":\"" + Esc(_Symbol) + "\",\"period_minutes\":" + IntegerToString(PeriodSeconds() / 60);
   s += ",\"chart_id\":" + IntegerToString(ChartID()) + "}";
   s += ",\"terminal\":{\"connected\":true,\"trade_allowed\":true,\"trade_allowed_expert\":true}";
   if(extra != "") s += extra;
   s += "}";
   return(s);
}

bool Post(const string json)
{
   char body[]; char key[];
   StringToCharArray(json, body, 0, StringLen(json));
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + InpPilotToken + "\r\n";
   ResetLastError();
   int code = WebRequest("POST", InpApiBase + "/pilot/ingest", headers, 10000, body, body, key);
   return(code == 200 || code == 202);
}

void SendEnvelope(const string type, const string extra)
{
   Post(Envelope(type, extra));
}

void SendTrade(ulong deal_ticket)
{
   if(!HistoryDealSelect(deal_ticket)) return;
   string e = "";
   e += ",\"trade\":{\"ticket\":" + IntegerToString(deal_ticket);
   e += ",\"position_id\":" + IntegerToString(HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID));
   e += ",\"magic\":\"" + IntegerToString(HistoryDealGetInteger(deal_ticket, DEAL_MAGIC)) + "\"";
   e += ",\"symbol\":\"" + Esc(HistoryDealGetString(deal_ticket, DEAL_SYMBOL)) + "\"";
   e += ",\"direction\":\"" + (HistoryDealGetInteger(deal_ticket, DEAL_TYPE) == DEAL_TYPE_BUY ? "buy" : "sell") + "\"";
   e += ",\"lots\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_VOLUME), 2);
   e += ",\"open_time\":\"" + TimeToString((datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME), TIME_DATE | TIME_SECONDS) + "Z\"";
   e += ",\"close_time\":\"" + TimeToString((datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME), TIME_DATE | TIME_SECONDS) + "Z\"";
   e += ",\"open_price\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_PRICE), 5);
   e += ",\"close_price\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_PRICE), 5);
   e += ",\"profit\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_PROFIT), 2);
   e += ",\"commission\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION), 2);
   e += ",\"swap\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_SWAP), 2);
   e += ",\"sl\":0,\"tp\":0,\"reason\":\"deal\"}";
   Post(Envelope("trade", e));
}
