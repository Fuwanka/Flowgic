/** Создание и редактирование делят форму и справочники своей компании. */
import { useEffect } from "react";
import {
  Alert,
  App,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
} from "antd";
import dayjs from "dayjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  createOrder,
  listClients,
  listDrivers,
  listVehicles,
  updateOrder,
} from "../client/sdk.gen";
import type {
  OrderCreateIn,
  OrderDetailOut,
  OrderOut,
} from "../client/types.gen";
import { read } from "../lib/api";
import { useTenantKey } from "../auth";
import { statuses } from "../lib/domain";
import { useMutationError } from "./common";

export function OrderForm({
  open,
  onClose,
  order,
}: {
  open: boolean;
  onClose: () => void;
  order?: OrderDetailOut;
}) {
  const key = useTenantKey();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const onError = useMutationError();
  const { message } = App.useApp();
  const clients = useQuery({
    queryKey: [...key, "clients"],
    queryFn: () => read(listClients()),
    enabled: open,
  });
  const drivers = useQuery({
    queryKey: [...key, "drivers"],
    queryFn: () => read(listDrivers()),
    enabled: open,
  });
  const vehicles = useQuery({
    queryKey: [...key, "vehicles"],
    queryFn: () => read(listVehicles()),
    enabled: open,
  });
  useEffect(() => {
    if (open) {
      form.resetFields();
      if (order)
        form.setFieldsValue({
          ...order,
          pickup_datetime: dayjs(order.pickup_datetime),
          delivery_datetime: dayjs(order.delivery_datetime),
        });
    }
  }, [open, order, form]);
  const save = useMutation<OrderOut, Error, OrderCreateIn>({
    mutationFn: (body: OrderCreateIn) =>
      order
        ? read(updateOrder({ path: { order_id: order.id }, body }))
        : read(createOrder({ body })),
    onSuccess: async (result) => {
      await cache.invalidateQueries({ queryKey: key });
      void message.success(order ? "Заказ обновлён" : "Заказ создан");
      onClose();
      navigate(`/orders/${result.id}`);
    },
    onError,
  });
  const lookupError = clients.error || drivers.error || vehicles.error;
  return (
    <Modal
      title={
        order ? `Редактирование заказа № ${order.order_number}` : "Новый заказ"
      }
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={save.isPending}
      okText={order ? "Сохранить" : "Создать заказ"}
      cancelText="Отмена"
      width={760}
      destroyOnHidden
    >
      {lookupError ? (
        <Alert
          type="error"
          title="Не удалось загрузить справочники"
          action={
            <a
              onClick={() => {
                void clients.refetch();
                void vehicles.refetch();
                void drivers.refetch();
              }}
            >
              Повторить
            </a>
          }
        />
      ) : (
        <>
          {clients.data?.length === 0 && (
            <Alert
              type="info"
              title={
                <>
                  Сначала{" "}
                  <Link to="/clients" onClick={onClose}>
                    добавьте клиента
                  </Link>{" "}
                  в справочник.
                </>
              }
            />
          )}
          <Form
            form={form}
            layout="vertical"
            initialValues={{ status: "created", cargo_mass_kg: 0 }}
            onFinish={(values) => {
              const body = {
                ...values,
                driver_id: values.driver_id ?? null,
                vehicle_id: values.vehicle_id ?? null,
                agreed_price: values.agreed_price ?? null,
                distance_km: values.distance_km ?? null,
                pickup_datetime: values.pickup_datetime.toISOString(),
                delivery_datetime: values.delivery_datetime.toISOString(),
              } as OrderCreateIn;
              save.mutate(body);
            }}
          >
            <Form.Item
              name="client_id"
              label="Клиент"
              rules={[{ required: true, message: "Выберите клиента" }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                loading={clients.isPending}
                options={clients.data?.map((c) => ({
                  value: c.id_client,
                  label: c.name,
                }))}
              />
            </Form.Item>
            <Row gutter={16}>
              <Col span={16}>
                <Form.Item
                  name="cargo_type"
                  label="Груз"
                  rules={[
                    {
                      required: true,
                      whitespace: true,
                      max: 100,
                      message: "Укажите груз (до 100 символов)",
                    },
                  ]}
                >
                  <Input placeholder="Например, строительные материалы" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="cargo_mass_kg"
                  label="Масса, кг"
                  rules={[{ required: true }]}
                >
                  <InputNumber
                    min={0}
                    max={2147483647}
                    precision={0}
                    className="full-width"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="origin" label="Откуда" rules={[{ max: 255 }]}>
                  <Input placeholder="Город, адрес погрузки" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="destination"
                  label="Куда"
                  rules={[{ max: 255 }]}
                >
                  <Input placeholder="Город, адрес выгрузки" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="pickup_datetime"
                  label="Погрузка"
                  rules={[{ required: true, message: "Укажите дату погрузки" }]}
                >
                  <DatePicker
                    showTime
                    format="DD.MM.YYYY HH:mm"
                    className="full-width"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="delivery_datetime"
                  label="Доставка"
                  dependencies={["pickup_datetime"]}
                  rules={[
                    { required: true, message: "Укажите дату доставки" },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        return !value ||
                          !getFieldValue("pickup_datetime") ||
                          !value.isBefore(getFieldValue("pickup_datetime"))
                          ? Promise.resolve()
                          : Promise.reject(
                              new Error("Доставка раньше погрузки"),
                            );
                      },
                    }),
                  ]}
                >
                  <DatePicker
                    showTime
                    format="DD.MM.YYYY HH:mm"
                    className="full-width"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="driver_id" label="Водитель">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    placeholder="Не назначен"
                    options={drivers.data
                      ?.filter((d) => d.status === "active")
                      .map((d) => ({
                        value: d.id,
                        label: d.full_name || d.email,
                      }))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="vehicle_id" label="Транспорт">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    placeholder="Не назначен"
                    options={vehicles.data
                      ?.filter((v) => v.status !== "blocked")
                      .map((v) => ({
                        value: v.id,
                        label: `${v.reg_number} · ${v.model ?? v.type}`,
                      }))}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="agreed_price" label="Стоимость, ₽">
                  <InputNumber
                    min={0}
                    max={99999999.99}
                    precision={2}
                    className="full-width"
                  />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="distance_km" label="Расстояние, км">
                  <InputNumber
                    min={0}
                    max={999999.99}
                    precision={2}
                    className="full-width"
                  />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="status" label="Статус">
                  <Select options={statuses} />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </>
      )}
    </Modal>
  );
}
