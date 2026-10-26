/** Финансовый предпросмотр приходит с сервера: фронтенд не дублирует формулу модели. */
import { useEffect, useState } from "react";
import {
  Alert,
  App,
  Button,
  Col,
  Form,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Tag,
} from "antd";
import { CalculatorOutlined, SaveOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { previewFinancials, saveFinancials } from "../client/sdk.gen";
import type {
  FinancialIn,
  FinancialOut,
  OrderDetailOut,
} from "../client/types.gen";
import { read } from "../lib/api";
import { money, paymentLabels } from "../lib/domain";
import { useTenantKey } from "../auth";
import { useMutationError } from "./common";

export function FinancialPanel({ order }: { order: OrderDetailOut }) {
  const [form] = Form.useForm();
  const [autoFuel, setAutoFuel] = useState(false);
  const [preview, setPreview] = useState<FinancialOut | null>(null);
  const key = useTenantKey();
  const cache = useQueryClient();
  const { message } = App.useApp();
  const onError = useMutationError();
  useEffect(() => {
    setPreview(null);
    setAutoFuel(false);
    form.setFieldsValue(
      order.financial ?? {
        client_cost: order.agreed_price ?? 0,
        driver_cost: 0,
        fuel_expenses: 0,
        third_party_cost: 0,
        payment_status: "unpaid",
      },
    );
  }, [order.financial, order.agreed_price, form]);
  const calculate = useMutation({
    mutationFn: (body: FinancialIn) =>
      read(previewFinancials({ path: { order_id: order.id }, body })),
    onSuccess: setPreview,
    onError,
  });
  const save = useMutation({
    mutationFn: (body: FinancialIn) =>
      read(saveFinancials({ path: { order_id: order.id }, body })),
    onSuccess: async () => {
      setPreview(null);
      await cache.invalidateQueries({ queryKey: key });
      void message.success("Финансовый расчёт сохранён");
    },
    onError,
  });
  const values = async () => {
    const data = await form.validateFields();
    return {
      ...data,
      fuel_expenses: autoFuel ? null : data.fuel_expenses,
      third_party_cost: data.third_party_cost ?? 0,
    } as FinancialIn;
  };
  const shown = preview ?? order.financial;
  const cost = Form.useWatch("client_cost", form);
  return (
    <section className="panel detail-panel" aria-label="Финансы">
      <div className="section-heading">
        <h2>
          <CalculatorOutlined aria-hidden="true" /> Финансы
        </h2>
        {shown && (
          <Tag color={shown.payment_status === "paid" ? "green" : "orange"}>
            {paymentLabels[shown.payment_status]}
          </Tag>
        )}
      </div>
      <Form
        form={form}
        layout="vertical"
        disabled={calculate.isPending || save.isPending}
        onValuesChange={() => setPreview(null)}
      >
        <Row gutter={16}>
          {[
            ["client_cost", "Стоимость заказчику, ₽"],
            ["driver_cost", "Выплата водителю, ₽"],
            ["fuel_expenses", "Топливо, ₽"],
            ["third_party_cost", "Прочие расходы, ₽"],
          ].map(([name, label]) => (
            <Col xs={24} sm={12} key={name}>
              <Form.Item
                name={name}
                label={label}
                rules={[
                  {
                    required:
                      name !== "third_party_cost" &&
                      !(name === "fuel_expenses" && autoFuel),
                    message: "Укажите сумму",
                  },
                ]}
              >
                <InputNumber
                  className="full-width"
                  min={0}
                  max={9999999999.99}
                  precision={2}
                  disabled={name === "fuel_expenses" && autoFuel}
                />
              </Form.Item>
            </Col>
          ))}
        </Row>
        <div className="auto-fuel">
          <Switch
            disabled={calculate.isPending || save.isPending}
            checked={autoFuel}
            aria-label="Автоматический расчёт топлива"
            onChange={(value) => {
              setAutoFuel(value);
              setPreview(null);
            }}
          />
          <span>Рассчитать топливо по пробегу</span>
        </div>
        <Form.Item name="payment_status" label="Статус оплаты">
          <Select
            options={Object.entries(paymentLabels).map(([value, label]) => ({
              value,
              label,
            }))}
          />
        </Form.Item>
        {order.agreed_price !== null &&
          cost !== undefined &&
          Number(cost) !== Number(order.agreed_price) && (
            <Alert
              type="info"
              title="Расчёт отличается от согласованной стоимости заказа."
              action={
                <Button
                  type="link"
                  onClick={() => {
                    form.setFieldValue("client_cost", order.agreed_price);
                    setPreview(null);
                  }}
                >
                  Подставить стоимость заказа
                </Button>
              }
            />
          )}
        <div
          className={`profit-box ${shown && Number(shown.profit) < 0 ? "profit-loss" : ""}`}
        >
          <div>
            <span>
              {preview ? "Предпросмотр прибыли" : "Сохранённая прибыль"}
            </span>
            <strong data-testid="profit">
              {shown ? money(shown.profit) : "Не рассчитана"}
            </strong>
          </div>
          {preview && (
            <small>
              Топливо: {money(preview.fuel_expenses)} · ещё не сохранено
            </small>
          )}
        </div>
        <p className="financial-rule">
          Стоимость − водитель − топливо. Прочие расходы хранятся отдельно и не
          входят в текущую формулу прибыли.
        </p>
        {autoFuel && !Number(order.distance_km) && (
          <Alert
            type="info"
            title="В заказе не задан пробег: автоматические расходы на топливо будут нулевыми."
          />
        )}
        <Space wrap>
          <Button
            icon={<CalculatorOutlined aria-hidden="true" />}
            loading={calculate.isPending}
            onClick={() =>
              void values()
                .then((body) => calculate.mutate(body))
                .catch(() => {})
            }
          >
            Рассчитать
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined aria-hidden="true" />}
            loading={save.isPending}
            onClick={() =>
              void values()
                .then((body) => save.mutate(body))
                .catch(() => {})
            }
          >
            Сохранить расчёт
          </Button>
        </Space>
      </Form>
    </section>
  );
}
