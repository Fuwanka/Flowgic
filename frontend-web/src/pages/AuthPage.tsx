/** Общие страницы входа, регистрации и восстановления пароля. */
import { useState } from "react";
import { Alert, Button, Form, Input, Select, Steps } from "antd";
import {
  ArrowRightOutlined,
  LockOutlined,
  MailOutlined,
} from "@ant-design/icons";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { errorMessage, read } from "../lib/api";
import { confirmPasswordReset, requestPasswordReset } from "../client/sdk.gen";

export function AuthPage({
  mode = "login",
}: {
  mode?: "login" | "register" | "reset";
}) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [resetStep, setResetStep] = useState(0);
  if (auth.user) return <Navigate to="/orders" replace />;
  const register = mode === "register";
  const reset = mode === "reset";
  return (
    <div className="auth-layout">
      <aside className="auth-story">
        <Link to="/login" className="brand">
          <span className="brand-mark">F</span>flowgic
          <span className="brand-dot">.</span>
        </Link>
        <div className="auth-copy">
          <span className="eyebrow">ЕДИНОЕ ПРОСТРАНСТВО КОМАНДЫ</span>
          <h1>
            Перевозки.
            <br />
            Люди. <span>Порядок.</span>
          </h1>
          <p>
            От первого звонка клиента до закрытого рейса — вся логистика перед
            вами.
          </p>
          <div className="route-illustration" aria-hidden="true">
            <div>
              <i />
              Заявка принята<span>01</span>
            </div>
            <b />
            <div>
              <i />
              Машина в пути<span>02</span>
            </div>
            <b />
            <div>
              <i />
              Рейс завершён<span>03</span>
            </div>
          </div>
        </div>
        <small>Flowgic · Управление перевозками</small>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <div className="auth-mobile-brand brand">
            <span className="brand-mark">F</span>flowgic.
          </div>
          <span className="eyebrow">ВАША ЛОГИСТИКА НАЧИНАЕТСЯ ЗДЕСЬ</span>
          <h2>
            {reset
              ? "Восстановление доступа"
              : register
                ? "Создайте компанию"
                : "С возвращением"}
          </h2>
          <p className="muted">
            {reset
              ? "Получите код на email и задайте новый пароль."
              : register
                ? "Начните с бесплатного тарифа: 3 машины и 30 заказов в месяц."
                : "Войдите в рабочее пространство своей команды."}
          </p>
          {error && (
            <Alert type="error" showIcon title={error} className="form-alert" />
          )}
          {reset ? (
            <>
              <Steps
                size="small"
                current={resetStep}
                items={[{ title: "Email" }, { title: "Новый пароль" }]}
              />
              <Form
                key={resetStep}
                layout="vertical"
                onFinish={async (values) => {
                  setBusy(true);
                  setError("");
                  try {
                    if (resetStep === 0) {
                      await read(
                        requestPasswordReset({ body: { email: values.email } }),
                      );
                      setEmail(values.email);
                      setResetStep(1);
                    } else {
                      await read(
                        confirmPasswordReset({
                          body: {
                            email,
                            code: values.code,
                            new_password: values.password,
                          },
                        }),
                      );
                      navigate("/login", { state: { passwordReset: true } });
                    }
                  } catch (e) {
                    setError(errorMessage(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {resetStep === 0 ? (
                  <Form.Item
                    name="email"
                    label="Email"
                    rules={[
                      {
                        required: true,
                        type: "email",
                        message: "Введите email",
                      },
                    ]}
                  >
                    <Input autoComplete="email" size="large" />
                  </Form.Item>
                ) : (
                  <>
                    <p className="muted">
                      Если аккаунт существует, код отправлен на {email}.
                    </p>
                    <Form.Item
                      name="code"
                      label="Код из письма"
                      rules={[
                        {
                          required: true,
                          pattern: /^\d{6}$/,
                          message: "Введите 6 цифр",
                        },
                      ]}
                    >
                      <Input autoComplete="one-time-code" maxLength={6} />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      label="Новый пароль"
                      rules={[
                        {
                          required: true,
                          min: 8,
                          message: "Не менее 8 символов",
                        },
                      ]}
                    >
                      <Input.Password autoComplete="new-password" />
                    </Form.Item>
                  </>
                )}
                <Button
                  htmlType="submit"
                  type="primary"
                  block
                  size="large"
                  loading={busy}
                >
                  {resetStep === 0 ? "Получить код" : "Сохранить пароль"}
                </Button>
              </Form>
              <p className="auth-switch">
                <Link to="/login">Вернуться ко входу</Link>
              </p>
            </>
          ) : (
            <>
              <Form
                layout="vertical"
                requiredMark={false}
                onFinish={async (values) => {
                  setBusy(true);
                  setError("");
                  try {
                    if (register) await auth.register(values);
                    else await auth.login(values);
                    navigate("/orders", { replace: true });
                  } catch (e) {
                    setError(errorMessage(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {register && (
                  <>
                    <Form.Item
                      name="full_name"
                      label="Ваше имя"
                      rules={[
                        {
                          required: true,
                          whitespace: true,
                          max: 255,
                          message: "Укажите имя",
                        },
                      ]}
                    >
                      <Input size="large" autoComplete="name" />
                    </Form.Item>
                    <Form.Item
                      name="company_name"
                      label="Название компании"
                      rules={[
                        {
                          required: true,
                          whitespace: true,
                          max: 255,
                          message: "Укажите компанию",
                        },
                      ]}
                    >
                      <Input size="large" autoComplete="organization" />
                    </Form.Item>
                    <Form.Item
                      name="company_type"
                      label="Направление работы"
                      initialValue="logistics"
                    >
                      <Select
                        size="large"
                        options={[
                          {
                            value: "logistics",
                            label: "Логистика и перевозки",
                          },
                          { value: "manufacturer", label: "Производство" },
                          { value: "retail", label: "Розничная торговля" },
                          {
                            value: "government",
                            label: "Государственная организация",
                          },
                        ]}
                      />
                    </Form.Item>
                  </>
                )}
                <Form.Item
                  name="email"
                  label="Рабочий email"
                  rules={[
                    {
                      required: true,
                      type: "email",
                      message: "Введите корректный email",
                    },
                  ]}
                >
                  <Input
                    size="large"
                    prefix={<MailOutlined aria-hidden="true" />}
                    autoComplete="email"
                    placeholder="name@company.ru"
                  />
                </Form.Item>
                <Form.Item
                  name="password"
                  label="Пароль"
                  rules={[
                    {
                      required: true,
                      min: register ? 8 : 1,
                      max: 128,
                      message: register
                        ? "От 8 до 128 символов"
                        : "Введите пароль",
                    },
                  ]}
                >
                  <Input.Password
                    size="large"
                    prefix={<LockOutlined aria-hidden="true" />}
                    autoComplete={
                      register ? "new-password" : "current-password"
                    }
                  />
                </Form.Item>
                {!register && (
                  <div className="forgot-link">
                    <Link to="/reset-password">Забыли пароль?</Link>
                  </div>
                )}
                <Button
                  htmlType="submit"
                  type="primary"
                  block
                  size="large"
                  icon={<ArrowRightOutlined aria-hidden="true" />}
                  loading={busy}
                >
                  {register
                    ? "Создать рабочее пространство"
                    : "Войти в Flowgic"}
                </Button>
              </Form>
              <p className="auth-switch">
                {register ? "Уже есть аккаунт?" : "Впервые в Flowgic?"}{" "}
                <Link to={register ? "/login" : "/register"}>
                  {register ? "Войти" : "Создать компанию"}
                </Link>
              </p>
            </>
          )}
          <p className="auth-footnote">
            Данные вашей компании доступны только её команде.
          </p>
        </div>
      </main>
    </div>
  );
}
