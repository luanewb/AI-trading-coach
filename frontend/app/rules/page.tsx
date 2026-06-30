"use client";

import { useEffect, useState } from "react";
import { Plus, PlayCircle, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { RiskRule, RuleCatalog, RuleCatalogCreate } from "@/lib/types";

const emptyRule: Omit<RiskRule, "id" | "account_id"> = {
  max_trades_per_day: 5,
  max_daily_loss_percent: "5",
  max_total_loss_percent: "10",
  max_consecutive_losses: 3,
  cooldown_minutes_after_loss: 30,
  max_lot: "1",
  max_risk_per_trade_percent: "1",
  allow_trading: true
};

const emptyCatalogRule: RuleCatalogCreate = {
  name: "",
  code: "",
  description: "",
  enabled: true,
  severity: "warning",
  action: "warn",
  category: "risk",
  config: {},
  message: ""
};

const severityOptions: RuleCatalog["severity"][] = ["info", "warning", "critical"];
const actionOptions: RuleCatalog["action"][] = ["allow", "warn", "block", "lock"];
const categoryOptions: RuleCatalog["category"][] = ["risk", "behavior", "ftmo", "execution", "psychology"];
const builtInRuleCodes = new Set([
  "PLATFORM_TRADING_ALLOWED",
  "NO_STOP_LOSS",
  "MAX_TRADES_PER_DAY",
  "MAX_DAILY_LOSS",
  "MAX_TOTAL_LOSS",
  "MAX_DRAWDOWN_LIMIT",
  "MAX_CONSECUTIVE_LOSSES",
  "COOLDOWN_AFTER_LOSS",
  "MAX_LOT_SIZE",
  "RISK_PER_TRADE",
  "REVENGE_TRADING"
]);

export default function RulesPage() {
  const [rule, setRule] = useState(emptyRule);
  const [catalog, setCatalog] = useState<RuleCatalog[]>([]);
  const [newRule, setNewRule] = useState<RuleCatalogCreate>(emptyCatalogRule);
  const [configText, setConfigText] = useState("{}");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.rules(), api.ruleCatalog()])
      .then(([{ id, account_id, ...data }, rules]) => {
        setRule(data);
        setCatalog(rules);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load rules"));
  }, []);

  async function save() {
    setStatus(null);
    setError(null);
    try {
      await api.updateRules(rule);
      setStatus("Rules saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save rules");
    }
  }

  async function evaluate() {
    setStatus(null);
    setError(null);
    try {
      const result = await api.evaluateRules();
      setStatus(`Evaluation: ${result.status}. Alerts: ${result.alerts_created.join(", ") || "none"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to evaluate rules");
    }
  }

  async function addCatalogRule() {
    setStatus(null);
    setError(null);
    try {
      const parsedConfig = configText.trim() ? JSON.parse(configText) : {};
      const created = await api.createRule({ ...newRule, config: parsedConfig });
      setCatalog((rules) => [...rules, created].sort((left, right) => left.code.localeCompare(right.code)));
      setNewRule(emptyCatalogRule);
      setConfigText("{}");
      setStatus(`Rule ${created.code} added.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add rule");
    }
  }

  async function updateCatalogRule(code: string, patch: Partial<RuleCatalogCreate>) {
    setStatus(null);
    setError(null);
    try {
      const updated = await api.updateRuleCatalog(code, patch);
      setCatalog((rules) => rules.map((item) => (item.code === code ? updated : item)));
      setStatus(`Rule ${updated.code} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update rule");
    }
  }

  async function deleteCatalogRule(code: string) {
    if (!window.confirm(`Delete rule ${code}?`)) {
      return;
    }
    setStatus(null);
    setError(null);
    try {
      await api.deleteRuleCatalog(code);
      setCatalog((rules) => rules.filter((item) => item.code !== code));
      setStatus(`Rule ${code} deleted.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete rule");
    }
  }

  function normalizeCode(value: string) {
    return value.toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/_+/g, "_");
  }

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Rules</p>
          <h2 className="page-title">Risk configuration</h2>
        </div>
      </header>

      <section className="panel mt-5 grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Max trades/day</span>
          <input className="input-field w-full" type="number" min={1} value={rule.max_trades_per_day} onChange={(event) => setRule({ ...rule, max_trades_per_day: Number(event.target.value) })} />
        </label>
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Max daily loss %</span>
          <input className="input-field w-full" type="number" step="0.1" value={rule.max_daily_loss_percent} onChange={(event) => setRule({ ...rule, max_daily_loss_percent: event.target.value })} />
        </label>
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Max total loss %</span>
          <input className="input-field w-full" type="number" step="0.1" value={rule.max_total_loss_percent} onChange={(event) => setRule({ ...rule, max_total_loss_percent: event.target.value })} />
        </label>
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Max consecutive losses</span>
          <input className="input-field w-full" type="number" min={1} value={rule.max_consecutive_losses} onChange={(event) => setRule({ ...rule, max_consecutive_losses: Number(event.target.value) })} />
        </label>
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Cooldown minutes</span>
          <input className="input-field w-full" type="number" min={0} value={rule.cooldown_minutes_after_loss} onChange={(event) => setRule({ ...rule, cooldown_minutes_after_loss: Number(event.target.value) })} />
        </label>
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Max lot</span>
          <input className="input-field w-full" type="number" step="0.01" value={rule.max_lot} onChange={(event) => setRule({ ...rule, max_lot: event.target.value })} />
        </label>
        <label className="space-y-2 text-sm font-medium text-zinc-200">
          <span>Max risk/trade %</span>
          <input className="input-field w-full" type="number" step="0.1" value={rule.max_risk_per_trade_percent} onChange={(event) => setRule({ ...rule, max_risk_per_trade_percent: event.target.value })} />
        </label>
        <label className="panel-soft flex h-11 items-center gap-3 px-3 text-sm font-medium text-zinc-200">
          <input className="h-5 w-5 accent-accent" type="checkbox" checked={rule.allow_trading} onChange={(event) => setRule({ ...rule, allow_trading: event.target.checked })} />
          Allow trading at platform level
        </label>
      </section>

      <div className="mt-5 flex flex-wrap gap-3">
        <button className="primary-action" onClick={save}>
          <Save size={16} aria-hidden />
          Save Rules
        </button>
        <button className="secondary-action" onClick={evaluate}>
          <PlayCircle size={16} aria-hidden />
          Evaluate Now
        </button>
      </div>
      {status && <p className="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-400/10 p-3 text-sm text-good">{status}</p>}
      {error && <p className="mt-4 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-bad">{error}</p>}

      <section className="mt-8">
        <header className="page-header">
          <div>
            <p className="kicker">Rule catalog</p>
            <h2 className="page-title">Custom rules</h2>
          </div>
        </header>

        <div className="panel mt-5 grid gap-4 p-5 lg:grid-cols-[1fr_360px]">
          <div className="space-y-3">
            {catalog.map((item) => (
              <div key={item.code} className="panel-soft grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_140px_120px_110px_44px] md:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-zinc-100">{item.name}</span>
                    <span className="rounded border border-white/10 px-2 py-0.5 text-xs text-zinc-400">{item.code}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-zinc-400">{item.message}</p>
                </div>
                <select className="input-field h-10 w-full" value={item.action} onChange={(event) => updateCatalogRule(item.code, { action: event.target.value as RuleCatalog["action"] })}>
                  {actionOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
                <select className="input-field h-10 w-full" value={item.severity} onChange={(event) => updateCatalogRule(item.code, { severity: event.target.value as RuleCatalog["severity"] })}>
                  {severityOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
                <label className="flex h-10 items-center gap-2 text-sm font-medium text-zinc-200">
                  <input className="h-5 w-5 accent-accent" type="checkbox" checked={item.enabled} onChange={(event) => updateCatalogRule(item.code, { enabled: event.target.checked })} />
                  Enabled
                </label>
                <button
                  className="grid h-10 w-10 place-items-center rounded border border-red-400/30 text-red-300 transition hover:border-red-300/60 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:border-white/10 disabled:text-zinc-600 disabled:hover:bg-transparent"
                  onClick={() => deleteCatalogRule(item.code)}
                  disabled={builtInRuleCodes.has(item.code)}
                  title={builtInRuleCodes.has(item.code) ? "Built-in rules cannot be deleted" : "Delete rule"}
                  aria-label={`Delete ${item.code}`}
                >
                  <Trash2 size={16} aria-hidden />
                </button>
              </div>
            ))}
          </div>

          <div className="panel-soft space-y-3 p-4">
            <label className="space-y-2 text-sm font-medium text-zinc-200">
              <span>Name</span>
              <input className="input-field w-full" value={newRule.name} onChange={(event) => setNewRule({ ...newRule, name: event.target.value })} />
            </label>
            <label className="space-y-2 text-sm font-medium text-zinc-200">
              <span>Code</span>
              <input className="input-field w-full" value={newRule.code} onChange={(event) => setNewRule({ ...newRule, code: normalizeCode(event.target.value) })} />
            </label>
            <label className="space-y-2 text-sm font-medium text-zinc-200">
              <span>Message</span>
              <input className="input-field w-full" value={newRule.message} onChange={(event) => setNewRule({ ...newRule, message: event.target.value })} />
            </label>
            <label className="space-y-2 text-sm font-medium text-zinc-200">
              <span>Description</span>
              <textarea className="input-field min-h-20 w-full resize-none py-3" value={newRule.description} onChange={(event) => setNewRule({ ...newRule, description: event.target.value })} />
            </label>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
              <label className="space-y-2 text-sm font-medium text-zinc-200">
                <span>Action</span>
                <select className="input-field h-11 w-full" value={newRule.action} onChange={(event) => setNewRule({ ...newRule, action: event.target.value as RuleCatalog["action"] })}>
                  {actionOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
              <label className="space-y-2 text-sm font-medium text-zinc-200">
                <span>Severity</span>
                <select className="input-field h-11 w-full" value={newRule.severity} onChange={(event) => setNewRule({ ...newRule, severity: event.target.value as RuleCatalog["severity"] })}>
                  {severityOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
              <label className="space-y-2 text-sm font-medium text-zinc-200">
                <span>Category</span>
                <select className="input-field h-11 w-full" value={newRule.category} onChange={(event) => setNewRule({ ...newRule, category: event.target.value as RuleCatalog["category"] })}>
                  {categoryOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
            </div>
            <label className="space-y-2 text-sm font-medium text-zinc-200">
              <span>Config JSON</span>
              <textarea className="input-field min-h-20 w-full resize-none py-3 font-mono text-xs" value={configText} onChange={(event) => setConfigText(event.target.value)} />
            </label>
            <button className="primary-action w-full justify-center" onClick={addCatalogRule} disabled={!newRule.name || !newRule.code || !newRule.message}>
              <Plus size={16} aria-hidden />
              Add Rule
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
