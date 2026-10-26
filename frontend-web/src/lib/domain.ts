/** Подписи и форматирование; бизнес-расчёты выполняет backend. */
import type { OrderRowOut, VehicleOut } from "../client/types.gen";
export const statuses: {
  value: OrderRowOut["status"];
  label: string;
  color: string;
}[] = [
  { value: "created", label: "Создан", color: "default" },
  { value: "assigned", label: "Назначен", color: "blue" },
  { value: "loading", label: "Погрузка", color: "cyan" },
  { value: "in_transit", label: "В пути", color: "geekblue" },
  { value: "delivered", label: "Доставлен", color: "green" },
  { value: "completed", label: "Завершён", color: "success" },
  { value: "delayed", label: "Задержан", color: "orange" },
  { value: "cancelled", label: "Отменён", color: "default" },
];
export const vehicleStatuses: { value: VehicleOut["status"]; label: string }[] =
  [
    { value: "available", label: "Доступен" },
    { value: "in_trip", label: "В рейсе" },
    { value: "maintenance", label: "Обслуживание" },
    { value: "blocked", label: "Заблокирован" },
  ];
export const paymentLabels: Record<string, string> = {
  unpaid: "Не оплачен",
  partially_paid: "Частично оплачен",
  paid: "Оплачен",
};
export const money = (value: string | number | null | undefined) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(Number(value ?? 0));
export const dateTime = (value: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
export const formatCount = (value: number) =>
  new Intl.NumberFormat("ru-RU").format(value);
