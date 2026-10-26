/** Серверная пагинация и фильтры не загружают весь автопарк в браузер. */
import { useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  Select,
  Table,
  Tag,
  type TableColumnsType,
} from "antd";
import {
  ArrowRightOutlined,
  CalendarOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { getOverview, listOrders } from "../client/sdk.gen";
import type { OrderRowOut } from "../client/types.gen";
import { read } from "../lib/api";
import {
  dateTime,
  formatCount,
  money,
  paymentLabels,
  statuses,
} from "../lib/domain";
import { useTenantKey } from "../auth";
import { Failure, OrderStatus } from "../components/common";
import { OrderForm } from "../components/OrderForm";
import { CalendarModal } from "../components/CalendarModal";
import { OfferPanel } from "../components/OfferPanel";

export function OrdersPage() {
  const key = useTenantKey();
  const [params, setParams] = useSearchParams();
  const [create, setCreate] = useState(false);
  const [calendar, setCalendar] = useState(false);
  const status = statuses.find((s) => s.value === params.get("status"))?.value;
  const q = (params.get("q") ?? "").slice(0, 100);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const query = useQuery({
    queryKey: [...key, "orders", status, q, page],
    queryFn: ({ signal }) =>
      read(listOrders({ query: { status, q, page, page_size: 20 }, signal })),
    placeholderData: keepPreviousData,
  });
  const summary = useQuery({
    queryKey: [...key, "overview"],
    queryFn: ({ signal }) => read(getOverview({ signal })),
  });
  const filter = (name: string, value?: string) => {
    const next = new URLSearchParams(params);
    next.delete("page");
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  };
  const columns: TableColumnsType<OrderRowOut> = [
    {
      title: "Заказ / клиент",
      key: "order",
      width: 225,
      render: (_, order) => (
        <>
          <Link className="order-number" to={`/orders/${order.id}`}>
            № {order.order_number}
          </Link>
          <div className="cell-secondary">{order.client.name}</div>
        </>
      ),
    },
    {
      title: "Маршрут",
      key: "route",
      width: 260,
      render: (_, o) => (
        <>
          <div className="route-cell">
            {o.origin || "Не указан"} <ArrowRightOutlined aria-hidden="true" />{" "}
            {o.destination || "Не указан"}
          </div>
          <div className="cell-secondary">
            {o.cargo_type} · {formatCount(o.cargo_mass_kg)} кг
          </div>
        </>
      ),
    },
    {
      title: "Погрузка / доставка",
      key: "dates",
      width: 185,
      render: (_, o) => (
        <>
          <div>{dateTime(o.pickup_datetime)}</div>
          <div className="cell-secondary">{dateTime(o.delivery_datetime)}</div>
        </>
      ),
    },
    {
      title: "Ресурсы",
      key: "resources",
      width: 170,
      render: (_, o) => (
        <>
          <div>{o.vehicle?.reg_number ?? "ТС не назначено"}</div>
          <div className="cell-secondary">
            {o.driver?.full_name ?? "Без водителя"}
          </div>
        </>
      ),
    },
    {
      title: "Статус",
      key: "status",
      width: 135,
      render: (_, o) => <OrderStatus status={o.status} />,
    },
    {
      title: "Стоимость",
      key: "price",
      fixed: "right",
      align: "right",
      width: 160,
      render: (_, o) => (
        <>
          <strong className="tabular">{money(o.agreed_price)}</strong>
          <div className="cell-secondary">
            {o.financial
              ? paymentLabels[o.financial.payment_status]
              : "Нет расчёта"}
          </div>
        </>
      ),
    },
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ОПЕРАЦИОННЫЙ ОБЗОР</span>
          <h1>Перевозки под контролем</h1>
          <p>Все заказы, ресурсы и сроки — в одном месте.</p>
        </div>
        <div className="heading-actions">
          <Button
            icon={<CalendarOutlined aria-hidden="true" />}
            onClick={() => setCalendar(true)}
          >
            Календарь
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined aria-hidden="true" />}
            onClick={() => setCreate(true)}
          >
            Новый заказ
          </Button>
        </div>
      </div>
      {summary.isError ? (
        <Failure error={summary.error} retry={() => void summary.refetch()} />
      ) : (
        <div className="stats-grid">
          {[
            ["Всего заказов", summary.data?.total, "В рабочем пространстве"],
            [
              "Активные рейсы",
              summary.data?.active,
              "Требуют внимания команды",
            ],
            ["Завершено", summary.data?.completed, "Успешно закрытые рейсы"],
            [
              "Сумма за месяц",
              summary.data ? money(summary.data.monthly_revenue) : undefined,
              "Стоимость выставленных перевозок",
            ],
          ].map(([label, value, note], i) => (
            <Card
              key={String(label)}
              className={`stat-card stat-${i}`}
              loading={summary.isPending}
            >
              <span className="stat-label">{label}</span>
              <strong>{value ?? "—"}</strong>
              <small>{note}</small>
            </Card>
          ))}
        </div>
      )}
      {!!summary.data?.overdue && (
        <div className="attention-strip">
          <span className="attention-dot" />
          <strong>{summary.data.overdue} рейс.</strong> — срок доставки истёк.
          Проверьте актуальные статусы.
        </div>
      )}
      <section className="panel orders-panel" aria-label="Заказы">
        <div className="table-toolbar">
          <div className="table-title">
            <h2>Заказы</h2>
            <Tag>{query.data?.total ?? "…"}</Tag>
          </div>
          <div className="table-filters">
            <Input.Search
              key={q}
              defaultValue={q}
              maxLength={100}
              allowClear
              placeholder="Номер, клиент или маршрут"
              aria-label="Поиск заказов"
              onSearch={(value) => filter("q", value.trim())}
            />
            <Select
              aria-label="Фильтр статуса"
              value={status}
              allowClear
              placeholder="Все статусы"
              options={statuses}
              onChange={(value) => filter("status", value)}
            />
            <Button
              aria-label="Обновить заказы"
              icon={<ReloadOutlined aria-hidden="true" />}
              onClick={() => {
                void query.refetch();
                void summary.refetch();
              }}
            />
          </div>
        </div>
        {query.isError ? (
          <Failure error={query.error} retry={() => void query.refetch()} />
        ) : (
          <Table<OrderRowOut>
            rowKey="id"
            columns={columns}
            dataSource={query.data?.items}
            loading={query.isFetching}
            scroll={{ x: 1160 }}
            pagination={{
              current: page,
              pageSize: 20,
              total: query.data?.total,
              showSizeChanger: false,
              showTotal: (total) => `Всего ${total}`,
              onChange: (p) => {
                const next = new URLSearchParams(params);
                next.set("page", String(p));
                setParams(next);
              },
            }}
            locale={{
              emptyText: (
                <Empty
                  description={
                    q || status
                      ? "По выбранным фильтрам заказов нет"
                      : "Пока нет заказов"
                  }
                >
                  <Button type="primary" onClick={() => setCreate(true)}>
                    Создать заказ
                  </Button>
                </Empty>
              ),
            }}
          />
        )}
      </section>
      <OfferPanel />
      <OrderForm open={create} onClose={() => setCreate(false)} />
      <CalendarModal open={calendar} onClose={() => setCalendar(false)} />
    </>
  );
}
