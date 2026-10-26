/** Профиль — идентичность текущей вкладки; сервер повторно проверяет роль и компанию. */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getProfile,
  loginAccount,
  logoutAccount,
  registerAccount,
} from "./client/sdk.gen";
import type { LoginIn, ProfileOut, RegistrationIn } from "./client/types.gen";
import { read } from "./lib/api";
import {
  getSession,
  refreshSession,
  setSession,
  subscribeSession,
} from "./lib/session";

type Auth = {
  user: ProfileOut | null;
  loading: boolean;
  login: (body: LoginIn) => Promise<void>;
  register: (body: RegistrationIn) => Promise<void>;
  logout: () => Promise<void>;
};
const Context = createContext<Auth | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ProfileOut | null>(null);
  const [loading, setLoading] = useState(Boolean(getSession()));
  const cache = useQueryClient();
  useEffect(() => {
    let alive = true;
    const unsubscribe = subscribeSession(() => {
      if (!getSession()) {
        setUser(null);
        void cache.cancelQueries();
        cache.clear();
      }
    });
    if (getSession())
      read(getProfile())
        .then((profile) => {
          if (alive) setUser(profile);
        })
        .catch(() => {
          if (alive) setSession(null);
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    return () => {
      alive = false;
      unsubscribe();
    };
  }, [cache]);
  const login = async (body: LoginIn) => {
    const pair = await read(loginAccount({ body }));
    await cache.cancelQueries();
    cache.clear();
    setSession(pair);
    try {
      setUser(await read(getProfile()));
    } catch (error) {
      setSession(null);
      throw error;
    }
  };
  const register = async (body: RegistrationIn) => {
    const result = await read(registerAccount({ body }));
    await cache.cancelQueries();
    cache.clear();
    setSession(result.tokens);
    setUser(result.user);
  };
  const logout = async () => {
    try {
      // Получаем актуальную пару после возможной ротации, чтобы отозвать именно её.
      await refreshSession();
      const session = getSession();
      if (session)
        await read(logoutAccount({ body: { refresh: session.refresh } }));
    } finally {
      setSession(null);
      setUser(null);
      await cache.cancelQueries();
      cache.clear();
    }
  };
  return (
    <Context.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const context = useContext(Context);
  if (!context) throw new Error("AuthProvider is required");
  return context;
}
export const useTenantKey = () =>
  ["tenant", useAuth().user!.company.id_company] as const;
