/** Календарь запрашивает только видимый диапазон; многодневный рейс виден в каждый день. */
import { useState } from "react";
import { Alert, Badge, Calendar, Modal, Popover } from "antd";
import dayjs from "dayjs";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCalendar } from "../client/sdk.gen";
import { read } from "../lib/api";
import { useTenantKey } from "../auth";
import { Failure } from "./common";

export function CalendarModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [month, setMonth] = useState(dayjs());
  const key = useTenantKey();
  // Запас по суткам покрывает локальные границы дня при любом UTC-смещении браузера.
  const start = month
    .startOf("month")
    .startOf("week")
    .subtract(1, "day")
    .format("YYYY-MM-DD");
  const end = month
    .endOf("month")
    .endOf("week")
    .add(2, "day")
    .format("YYYY-MM-DD");
  const query = useQuery({
    queryKey: [...key, "calendar", start, end],
    enabled: open,
    queryFn: () => read(getCalendar({ query: { start, end } })),
  });
  return (
    <Modal
      title="Календарь перевозок"
      open={open}
      onCancel={onClose}
      footer={null}
      width={1150}
    >
      {query.isError ? (
        <Failure error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <p className="muted">
            Погрузка → доставка · Время указано в часовом поясе вашего
            устройства.
          </p>
          {query.data?.truncated && (
            <Alert
              type="warning"
              title="Показаны первые 1000 рейсов за период."
            />
          )}
          {query.isPending && <p role="status">Загрузка рейсов…</p>}
          <Calendar
            value={month}
            onChange={setMonth}
            mode="month"
            onPanelChange={setMonth}
            cellRender={(current, info) => {
              if (info.type !== "date") return info.originNode;
              const events =
                query.data?.items.filter(
                  (order) =>
                    !current.endOf("day").isBefore(order.pickup_datetime) &&
                    !current.startOf("day").isAfter(order.delivery_datetime),
                ) ?? [];
              const links = events.map((order) => (
                <Link
                  key={order.id}
                  to={`/orders/${order.id}`}
                  onClick={onClose}
                  className="calendar-order"
                >
                  № {order.order_number} · {order.client.name}
                </Link>
              ));
              return (
                <div className="calendar-events">
                  {links.slice(0, 2)}
                  {events.length > 2 && (
                    <Popover
                      content={<div className="calendar-popover">{links}</div>}
                      trigger="click"
                    >
                      <button className="more-events">
                        Ещё {events.length - 2}
                      </button>
                    </Popover>
                  )}
                  {events.length > 0 && (
                    <Badge
                      status="processing"
                      text={`${events.length} рейс.`}
                    />
                  )}
                </div>
              );
            }}
          />
        </>
      )}
    </Modal>
  );
}
