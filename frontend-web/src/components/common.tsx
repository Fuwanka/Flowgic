/** Повторно используемые состояния экрана и обработка тарифного ограничения. */
import { App, Button, Result, Spin, Tag } from "antd";
import { useNavigate } from "react-router-dom";
import { ApiError, errorMessage } from "../lib/api";
import { statuses } from "../lib/domain";
export function Loading() {
  return (
    <div className="loading-state">
      <Spin size="large" tip="Загрузка…">
        <div />
      </Spin>
    </div>
  );
}
export function Failure({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <Result
      status={
        error instanceof ApiError && error.status === 404 ? "404" : "warning"
      }
      title={
        error instanceof ApiError && error.status === 404
          ? "Запись не найдена"
          : "Не удалось загрузить данные"
      }
      subTitle={errorMessage(error)}
      extra={retry && <Button onClick={retry}>Попробовать снова</Button>}
    />
  );
}
export function OrderStatus({ status }: { status: string }) {
  const current = statuses.find((item) => item.value === status);
  return (
    <Tag color={current?.color} className="status-tag">
      {current?.label ?? status}
    </Tag>
  );
}
export function useMutationError() {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  return (error: unknown) => {
    if (error instanceof ApiError && error.status === 402) {
      modal.info({
        title: "Достигнут лимит тарифа",
        content: error.message,
        okText: "Посмотреть тарифы",
        onOk: () => navigate("/billing"),
      });
    } else {
      void message.error(errorMessage(error));
    }
  };
}
