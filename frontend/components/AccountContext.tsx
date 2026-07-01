"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { Account } from "@/lib/types";

type AccountContextValue = {
  accounts: Account[];
  selectedAccountId: number | null;
  selectedAccount: Account | null;
  loading: boolean;
  setSelectedAccountId: (accountId: number | null) => void;
  accountHref: (href: string) => string;
};

const AccountContext = createContext<AccountContextValue | null>(null);
const storageKey = "ai-trading-coach:selected-account-id";

function parseAccountId(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountIdState] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  function syncUrl(accountId: number | null) {
    const url = new URL(window.location.href);
    const params = url.searchParams;
    if (accountId) {
      params.set("account_id", String(accountId));
    } else {
      params.delete("account_id");
    }
    url.search = params.toString();
    router.replace(`${url.pathname}${url.search}`);
    router.refresh();
  }

  function setSelectedAccountId(accountId: number | null) {
    setSelectedAccountIdState(accountId);
    if (accountId) {
      window.localStorage.setItem(storageKey, String(accountId));
    } else {
      window.localStorage.removeItem(storageKey);
    }
    syncUrl(accountId);
  }

  useEffect(() => {
    const fromUrl = parseAccountId(new URL(window.location.href).searchParams.get("account_id"));
    const fromStorage = parseAccountId(window.localStorage.getItem(storageKey));
    setSelectedAccountIdState(fromUrl || fromStorage);

    api.accounts()
      .then(setAccounts)
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (loading || accounts.length === 0) return;
    const selectedExists = selectedAccountId !== null && accounts.some((account) => account.id === selectedAccountId);
    if (selectedExists) return;
    const fallback = accounts[0].id;
    setSelectedAccountIdState(fallback);
    window.localStorage.setItem(storageKey, String(fallback));
    if (!parseAccountId(new URL(window.location.href).searchParams.get("account_id"))) {
      syncUrl(fallback);
    }
  }, [accounts, loading, selectedAccountId]);

  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === selectedAccountId) || null,
    [accounts, selectedAccountId]
  );

  const value = useMemo<AccountContextValue>(
    () => ({
      accounts,
      selectedAccountId,
      selectedAccount,
      loading,
      setSelectedAccountId,
      accountHref: (href: string) => {
        if (!selectedAccountId) return href;
        const [path, rawQuery = ""] = href.split("?");
        const params = new URLSearchParams(rawQuery);
        params.set("account_id", String(selectedAccountId));
        const query = params.toString();
        return `${path}${query ? `?${query}` : ""}`;
      }
    }),
    [accounts, selectedAccount, selectedAccountId, loading]
  );

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useSelectedAccount() {
  const context = useContext(AccountContext);
  if (!context) {
    throw new Error("useSelectedAccount must be used inside AccountProvider");
  }
  return context;
}

export function AccountSwitcher() {
  const { accounts, selectedAccountId, selectedAccount, loading, setSelectedAccountId } = useSelectedAccount();

  if (loading) {
    return (
      <div className="mx-2 mt-6 rounded-xl border border-line bg-elevated p-3 text-sm text-zinc-400">
        <div className="flex items-center gap-2">
          <RefreshCw size={14} aria-hidden />
          Loading accounts
        </div>
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="mx-2 mt-6 rounded-xl border border-line bg-elevated p-3">
        <p className="text-xs font-medium text-zinc-500">MT5 Account</p>
        <p className="mt-1 text-sm font-semibold text-zinc-100">Waiting for heartbeat</p>
      </div>
    );
  }

  return (
    <label className="mx-2 mt-6 block rounded-xl border border-line bg-elevated p-3">
      <span className="text-xs font-medium text-zinc-500">MT5 Account</span>
      <select
        className="mt-2 h-10 w-full rounded-lg border border-line bg-paper px-2 text-sm font-semibold text-zinc-100 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
        value={selectedAccountId ?? ""}
        onChange={(event) => setSelectedAccountId(Number(event.target.value))}
      >
        {accounts.map((account) => (
          <option key={account.id} value={account.id}>
            {account.account_number} - {account.broker}
          </option>
        ))}
      </select>
      {selectedAccount && (
        <p className="mt-2 truncate text-xs text-zinc-500" title={`${selectedAccount.broker} / ${selectedAccount.server}`}>
          {selectedAccount.server}
        </p>
      )}
    </label>
  );
}
