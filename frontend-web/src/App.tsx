/** Маршрутизация и адаптивная оболочка. Клиентский guard дополняет серверный RBAC. */
import { lazy, Suspense, useState } from "react";
import { App as AntApp, Avatar, Button, Drawer, Result, Tag } from "antd";
import {
  CarOutlined,
  CreditCardOutlined,
  DashboardOutlined,
  LogoutOutlined,
  MenuOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { useAuth } from "./auth";
import { AuthPage } from "./pages/AuthPage";
import { Loading } from "./components/common";

// Разделы загружаются по маршруту: формы, календарь и финансовый редактор не нужны при входе.
const OrdersPage = lazy(() =>
  import("./pages/OrdersPage").then((m) => ({ default: m.OrdersPage })),
);
const OrderPage = lazy(() =>
  import("./pages/OrderPage").then((m) => ({ default: m.OrderPage })),
);
const DirectoryPage = lazy(() =>
  import("./pages/DirectoryPage").then((m) => ({ default: m.DirectoryPage })),
);
const BillingPage = lazy(() =>
  import("./pages/BillingPage").then((m) => ({ default: m.BillingPage })),
);

function Workspace() {
  const { user, loading, logout } = useAuth();
  const { message } = AntApp.useApp();
  const location = useLocation();
  const [mobileMenu, setMobileMenu] = useState(false);
  const signOut = () => {
    void logout().catch(() =>
      message.warning(
        "Локальная сессия удалена. Не удалось подтвердить выход на сервере.",
      ),
    );
  };
  if (loading) return <Loading />;
  if (!user)
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (!["dispatcher", "manager"].includes(user.role))
    return (
      <Result
        status="403"
        title="Кабинет команды"
        subTitle="Веб-панель доступна диспетчеру и руководителю. Ваш аккаунт водителя предназначен для водительского контура."
        extra={<Button onClick={signOut}>Выйти</Button>}
      />
    );
  const links = [
    {
      to: "/orders",
      title: "Заказы",
      icon: <DashboardOutlined aria-hidden="true" />,
    },
    {
      to: "/clients",
      title: "Клиенты",
      icon: <TeamOutlined aria-hidden="true" />,
    },
    {
      to: "/vehicles",
      title: "Транспорт",
      icon: <CarOutlined aria-hidden="true" />,
    },
    {
      to: "/drivers",
      title: "Водители",
      icon: <UserOutlined aria-hidden="true" />,
    },
    {
      to: "/billing",
      title: "Тариф и лимиты",
      icon: <CreditCardOutlined aria-hidden="true" />,
    },
  ];
  const navigation = (
    <div className="sidebar-inner">
      <NavLink
        to="/orders"
        className="brand"
        onClick={() => setMobileMenu(false)}
      >
        <span className="brand-mark">F</span>flowgic
        <span className="brand-dot">.</span>
      </NavLink>
      <div className="company-card">
        <span className="company-icon">{user.company.name.slice(0, 1)}</span>
        <div>
          <strong>{user.company.name}</strong>
          <small>Рабочее пространство</small>
        </div>
      </div>
      <span className="nav-label">УПРАВЛЕНИЕ</span>
      <nav aria-label="Основная навигация">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            onClick={() => setMobileMenu(false)}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            {link.icon}
            {link.title}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-note">
        <span className="eyebrow">ВСЁ НА СВОИХ МЕСТАХ</span>
        <p>
          Меньше рутины.
          <br />
          Больше завершённых рейсов.
        </p>
      </div>
      <div className="user-card">
        <Avatar style={{ background: "#d7eee7", color: "#185d52" }}>
          {user.full_name.slice(0, 1) || "F"}
        </Avatar>
        <div>
          <strong>{user.full_name || user.email}</strong>
          <small>
            {user.role === "manager" ? "Руководитель" : "Диспетчер"}
          </small>
        </div>
        <Button
          type="text"
          aria-label="Выйти"
          icon={<LogoutOutlined aria-hidden="true" />}
          onClick={signOut}
        />
      </div>
    </div>
  );
  return (
    <div className="workspace">
      <aside className="sidebar">{navigation}</aside>
      <Drawer
        open={mobileMenu}
        onClose={() => setMobileMenu(false)}
        placement="left"
        size={260}
        styles={{ body: { padding: 0, background: "#132d35" } }}
      >
        {navigation}
      </Drawer>
      <div className="workspace-main">
        <header className="topbar">
          <div>
            <Button
              className="mobile-menu-button"
              aria-label="Открыть навигацию"
              icon={<MenuOutlined aria-hidden="true" />}
              onClick={() => setMobileMenu(true)}
            />
            <span className="topbar-context">
              Рабочее пространство <span>/</span>{" "}
              {links.find((l) => location.pathname.startsWith(l.to))?.title ??
                "Flowgic"}
            </span>
          </div>
          <div className="topbar-right">
            <Tag bordered={false}>TMS / CRM</Tag>
            <span>
              {new Intl.DateTimeFormat("ru-RU", {
                day: "numeric",
                month: "long",
                year: "numeric",
              }).format(new Date())}
            </span>
          </div>
        </header>
        <main className="page-content">
          <Suspense fallback={<Loading />}>
            <Outlet />
          </Suspense>
        </main>
        <footer className="workspace-footer">
          <span>Flowgic · Логистика в порядке</span>
          <span>Время на экранах — по часовому поясу устройства</span>
        </footer>
      </div>
    </div>
  );
}
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/reset-password" element={<AuthPage mode="reset" />} />
      <Route element={<Workspace />}>
        <Route index element={<Navigate to="/orders" replace />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="orders/:id" element={<OrderPage />} />
        <Route path="clients" element={<DirectoryPage kind="clients" />} />
        <Route path="vehicles" element={<DirectoryPage kind="vehicles" />} />
        <Route path="drivers" element={<DirectoryPage kind="drivers" />} />
        <Route path="billing" element={<BillingPage />} />
        <Route
          path="*"
          element={
            <Result
              status="404"
              title="Страница не найдена"
              extra={<NavLink to="/orders">Вернуться к заказам</NavLink>}
            />
          }
        />
      </Route>
    </Routes>
  );
}
