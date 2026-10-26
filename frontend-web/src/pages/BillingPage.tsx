/** Каталог и фактическое использование тарифа. Смена плана остаётся административной операцией. */
import { Card, Progress, Tag } from "antd";
import { CheckCircleOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import {
  getCompanySubscription,
  listSubscriptionPlans,
} from "../client/sdk.gen";
import { useTenantKey } from "../auth";
import { read } from "../lib/api";
import { Failure, Loading } from "../components/common";
export function BillingPage() {
  const key = useTenantKey();
  const profile = useQuery({
    queryKey: [...key, "subscription"],
    queryFn: () => read(getCompanySubscription()),
  });
  const plans = useQuery({
    queryKey: [...key, "plans"],
    queryFn: () => read(listSubscriptionPlans()),
  });
  if (profile.isPending || plans.isPending) return <Loading />;
  if (profile.isError || plans.isError)
    return (
      <Failure
        error={profile.error ?? plans.error}
        retry={() => {
          void profile.refetch();
          void plans.refetch();
        }}
      />
    );
  const { plan, usage } = profile.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ВОЗМОЖНОСТИ КОМПАНИИ</span>
          <h1>Тариф и использование</h1>
          <p>Прозрачные ограничения для вашей команды и автопарка.</p>
        </div>
        <Tag color="cyan">Текущий тариф · {plan.plan_type}</Tag>
      </div>
      <div className="usage-grid">
        {[
          ["Активные ТС", usage.vehicles, plan.max_vehicles],
          [
            "Заказы в текущем месяце UTC",
            usage.orders,
            plan.max_orders_per_month,
          ],
        ].map(([label, count, limit]) => (
          <Card key={String(label)}>
            <h3>{label}</h3>
            <strong className="usage-number">
              {count} <small>/ {limit ?? "без лимита"}</small>
            </strong>
            <Progress
              percent={
                limit ? Math.min(100, (Number(count) / Number(limit)) * 100) : 0
              }
              showInfo={false}
              strokeColor="#16796b"
            />
          </Card>
        ))}
      </div>
      <div className="plans-grid">
        {plans.data.map((p) => (
          <Card
            key={p.plan_type}
            className={p.plan_type === plan.plan_type ? "current-plan" : ""}
          >
            <Tag color={p.plan_type === plan.plan_type ? "green" : undefined}>
              {p.plan_type}
            </Tag>
            <h2>{p.name}</h2>
            <p>
              <CheckCircleOutlined aria-hidden="true" />{" "}
              {p.max_vehicles ?? "Без ограничения"} ТС
            </p>
            <p>
              <CheckCircleOutlined aria-hidden="true" />{" "}
              {p.max_orders_per_month ?? "Без ограничения"} заказов в месяц
            </p>
            <p>
              <CheckCircleOutlined aria-hidden="true" />{" "}
              {p.iot_enabled ? "Доступ к IoT" : "Базовые возможности"}
            </p>
            {p.plan_type === plan.plan_type && (
              <strong className="plan-current">Ваш тариф</strong>
            )}
          </Card>
        ))}
      </div>
      <p className="muted">
        Для изменения тарифа обратитесь к администратору. Оплата в приложении
        пока не подключена. Заблокированные ТС не расходуют лимит активного
        автопарка.
      </p>
    </>
  );
}
