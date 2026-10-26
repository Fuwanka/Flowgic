/** Карточка связывает маршрут, назначение ресурсов, расчёт, историю и документы. */
import { useState } from "react";
import {
  App,
  Button,
  Descriptions,
  Select,
  Space,
  Timeline,
  Tooltip,
} from "antd";
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  DownloadOutlined,
  EditOutlined,
  EnvironmentOutlined,
  HistoryOutlined,
} from "@ant-design/icons";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  changeOrderStatus,
  downloadOrderDocument,
  getOrder,
} from "../client/sdk.gen";
import type { OrderStatusIn } from "../client/types.gen";
import { read, saveBlob } from "../lib/api";
import { dateTime, formatCount, money, statuses } from "../lib/domain";
import { useTenantKey } from "../auth";
import {
  Failure,
  Loading,
  OrderStatus,
  useMutationError,
} from "../components/common";
import { OrderForm } from "../components/OrderForm";
import { FinancialPanel } from "../components/FinancialPanel";
import { OfferPanel } from "../components/OfferPanel";

export function OrderPage() {
  const { id = "" } = useParams();
  const key = useTenantKey();
  const cache = useQueryClient();
  const [edit, setEdit] = useState(false);
  const { message } = App.useApp();
  const onError = useMutationError();
  const query = useQuery({
    queryKey: [...key, "order", id],
    queryFn: ({ signal }) => read(getOrder({ path: { order_id: id }, signal })),
  });
  const status = useMutation({
    mutationFn: (body: OrderStatusIn) =>
      read(changeOrderStatus({ path: { order_id: id }, body })),
    onError,
    onSuccess: async () => {
      await cache.invalidateQueries({ queryKey: key });
      void message.success("Статус обновлён");
    },
  });
  const document = useMutation({
    mutationFn: (type: "application" | "ttn") =>
      read(
        downloadOrderDocument({
          path: { order_id: id },
          query: { document_type: type },
        }),
      ),
    onError,
  });
  if (query.isPending) return <Loading />;
  if (query.isError)
    return <Failure error={query.error} retry={() => void query.refetch()} />;
  const order = query.data;
  const download = (type: "application" | "ttn") =>
    document.mutate(type, {
      onSuccess: (blob) =>
        saveBlob(blob, `order-${order.order_number}-${type}.docx`),
    });
  return (
    <>
      <Link to="/orders" className="back-link">
        <ArrowLeftOutlined aria-hidden="true" /> Все заказы
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <span className="eyebrow">КАРТОЧКА ПЕРЕВОЗКИ</span>
          <h1>
            Заказ № {order.order_number} <OrderStatus status={order.status} />
          </h1>
          <p>
            {order.client.name} · Создан {dateTime(order.created_at)}
          </p>
        </div>
        <div className="heading-actions">
          <Button
            icon={<EditOutlined aria-hidden="true" />}
            onClick={() => setEdit(true)}
          >
            Редактировать
          </Button>
          <Tooltip title="Редактируемый черновик по данным заказа">
            <Button
              type="primary"
              icon={<DownloadOutlined aria-hidden="true" />}
              loading={document.isPending}
              onClick={() => download("application")}
            >
              Скачать заявку
            </Button>
          </Tooltip>
        </div>
      </div>
      <div className="detail-grid">
        <div className="detail-main">
          <section className="panel detail-panel">
            <div className="section-heading">
              <h2>
                <EnvironmentOutlined aria-hidden="true" /> Маршрут и груз
              </h2>
              <span>
                {order.distance_km
                  ? `${formatCount(Number(order.distance_km))} км`
                  : "Пробег не указан"}
              </span>
            </div>
            <div className="route-overview">
              <div className="route-stop">
                <span className="route-dot" />
                <small>ПОГРУЗКА</small>
                <h3>{order.origin || "Не указана"}</h3>
                <time>{dateTime(order.pickup_datetime)}</time>
              </div>
              <ArrowRightOutlined aria-hidden="true" className="route-arrow" />
              <div className="route-stop">
                <span className="route-dot destination" />
                <small>ДОСТАВКА</small>
                <h3>{order.destination || "Не указана"}</h3>
                <time>{dateTime(order.delivery_datetime)}</time>
              </div>
            </div>
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2 }}
              items={[
                { key: "cargo", label: "Груз", children: order.cargo_type },
                {
                  key: "weight",
                  label: "Масса",
                  children: `${formatCount(order.cargo_mass_kg)} кг`,
                },
                {
                  key: "price",
                  label: "Стоимость",
                  children: money(order.agreed_price),
                },
                {
                  key: "phone",
                  label: "Контакт клиента",
                  children:
                    order.client.phone ?? order.client.email ?? "Не указан",
                },
              ]}
            />
          </section>
          <section className="panel detail-panel">
            <div className="section-heading">
              <h2>Ресурсы и выполнение</h2>
              <Button type="link" onClick={() => setEdit(true)}>
                Назначить ресурсы
              </Button>
            </div>
            <div className="resource-grid">
              <div>
                <span className="muted">Водитель</span>
                <h3>{order.driver?.full_name ?? "Не назначен"}</h3>
                <small>{order.driver?.phone ?? "Телефон не указан"}</small>
              </div>
              <div>
                <span className="muted">Транспорт</span>
                <h3>{order.vehicle?.reg_number ?? "Не назначен"}</h3>
                <small>
                  {order.vehicle?.model ??
                    order.vehicle?.type ??
                    "Выберите ТС для рейса"}
                </small>
              </div>
            </div>
            <div className="status-editor">
              <label htmlFor="order-status">Статус заказа</label>
              <Select
                id="order-status"
                aria-label="Статус заказа"
                options={statuses}
                value={order.status}
                disabled={status.isPending}
                onChange={(value) => status.mutate({ status: value })}
              />
            </div>
            {order.delay_reason && (
              <p className="attention-strip">{order.delay_reason}</p>
            )}
          </section>
          <section className="panel detail-panel">
            <div className="section-heading">
              <h2>
                <HistoryOutlined aria-hidden="true" /> История заказа
              </h2>
              <span>Последние 100 событий</span>
            </div>
            {order.events.length === 0 ? (
              <p className="muted">Изменений пока нет.</p>
            ) : (
              <Timeline
                items={order.events.map((event) => {
                  const data = event.event_data ?? {};
                  const label =
                    event.event_type === "payment_updated"
                      ? "Обновлены финансы или оплата"
                      : data.action === "order_edited"
                        ? "Изменены данные заказа"
                        : "Изменён статус";
                  const next =
                    typeof data.new_status === "string"
                      ? statuses.find((s) => s.value === data.new_status)?.label
                      : null;
                  return {
                    content: (
                      <div>
                        <strong>
                          {label}
                          {next ? ` · ${next}` : ""}
                        </strong>
                        <div className="cell-secondary">
                          {dateTime(event.created_at)}
                        </div>
                      </div>
                    ),
                  };
                })}
              />
            )}
          </section>
        </div>
        <aside className="detail-side">
          <FinancialPanel order={order} />
          <section className="panel detail-panel">
            <h2>Документы перевозки</h2>
            <p className="muted">
              Редактируемые черновики. Дополните реквизиты и проверьте документ
              перед подписанием.
            </p>
            <Space orientation="vertical" className="full-width">
              <Button
                block
                icon={<DownloadOutlined aria-hidden="true" />}
                loading={document.isPending}
                onClick={() => download("application")}
              >
                Договор-заявка DOCX
              </Button>
              <Button
                block
                icon={<DownloadOutlined aria-hidden="true" />}
                loading={document.isPending}
                onClick={() => download("ttn")}
              >
                ТТН DOCX
              </Button>
            </Space>
          </section>
        </aside>
      </div>
      <OfferPanel orderId={id} />
      <OrderForm open={edit} onClose={() => setEdit(false)} order={order} />
    </>
  );
}
