/** Общая оболочка справочников; отдельные DTO сохраняют границы accounts/logistics. */
import { useEffect, useState } from "react";
import {
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Table,
  Tag,
  type TableColumnsType,
} from "antd";
import { EditOutlined, PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createClient,
  createDriver,
  createVehicle,
  listClients,
  listDrivers,
  listVehicles,
  updateClient,
  updateDriver,
  updateVehicle,
} from "../client/sdk.gen";
import type {
  ClientIn,
  ClientOut,
  DriverCreateIn,
  DriverUpdateIn,
  DriverOut,
  VehicleCreateIn,
  VehicleOut,
} from "../client/types.gen";
import { read } from "../lib/api";
import { vehicleStatuses } from "../lib/domain";
import { useTenantKey } from "../auth";
import { Failure, useMutationError } from "../components/common";

type Kind = "clients" | "vehicles" | "drivers";
type Row = {
  key: string;
  name: string;
  description: string;
  contact: string;
  status?: string;
  raw: ClientOut | VehicleOut | DriverOut;
};
const titles = {
  clients: [
    "Клиенты",
    "Заказчики перевозок и контактные данные",
    "Добавить клиента",
  ],
  vehicles: [
    "Транспорт",
    "Автопарк, грузоподъёмность и готовность к рейсу",
    "Добавить транспорт",
  ],
  drivers: [
    "Водители",
    "Команда водителей вашей компании",
    "Добавить водителя",
  ],
};
export function DirectoryPage({ kind }: { kind: Kind }) {
  const key = useTenantKey();
  const cache = useQueryClient();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const [form] = Form.useForm();
  const onError = useMutationError();
  const { message } = App.useApp();
  const query = useQuery({
    // Здесь кешируется представление Row, а формы используют сырой DTO под другим ключом.
    queryKey: [...key, "directory", kind],
    queryFn: async ({ signal }): Promise<Row[]> => {
      if (kind === "clients")
        return (await read(listClients({ signal }))).map((c) => ({
          key: c.id_client,
          name: c.name,
          description: c.email ?? "Email не указан",
          contact: c.phone ?? "Телефон не указан",
          raw: c,
        }));
      if (kind === "vehicles")
        return (await read(listVehicles({ signal }))).map((v) => ({
          key: v.id,
          name: v.reg_number,
          description: `${v.model ?? v.type} · ${v.capacity_kg} кг`,
          contact: v.type,
          status: v.status,
          raw: v,
        }));
      return (await read(listDrivers({ signal }))).map((d) => ({
        key: String(d.id),
        name: d.full_name || d.email,
        description: d.email,
        contact: d.phone ?? "Телефон не указан",
        status: d.status,
        raw: d,
      }));
    },
    select: (data) => data,
  });
  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue(
        editing?.raw ?? {
          status: kind === "vehicles" ? "available" : "active",
          capacity_kg: 0,
        },
      );
    }
  }, [open, editing, form, kind]);
  useEffect(() => {
    setSearch("");
    setOpen(false);
    setEditing(null);
  }, [kind]);
  const save = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      if (kind === "clients")
        return editing
          ? read(
              updateClient({
                path: { client_id: editing.key },
                body: values as ClientIn,
              }),
            )
          : read(createClient({ body: values as ClientIn }));
      if (kind === "vehicles")
        return editing
          ? read(
              updateVehicle({
                path: { vehicle_id: editing.key },
                body: values as VehicleCreateIn,
              }),
            )
          : read(createVehicle({ body: values as VehicleCreateIn }));
      if (editing)
        return read(
          updateDriver({
            path: { driver_id: Number(editing.key) },
            body: {
              full_name: String(values.full_name),
              phone: values.phone as string | null,
              status: values.status as DriverUpdateIn["status"],
            },
          }),
        );
      return read(createDriver({ body: values as DriverCreateIn }));
    },
    onError,
    onSuccess: async () => {
      await cache.invalidateQueries({ queryKey: key });
      setOpen(false);
      form.resetFields();
      void message.success("Данные сохранены");
    },
  });
  const columns: TableColumnsType<Row> = [
    {
      title: kind === "vehicles" ? "Транспорт" : "Название / имя",
      key: "name",
      render: (_, row) => (
        <>
          <strong>{row.name}</strong>
          <div className="cell-secondary">{row.description}</div>
        </>
      ),
    },
    {
      title: kind === "vehicles" ? "Тип" : "Телефон",
      dataIndex: "contact",
      key: "contact",
    },
    ...(kind === "clients"
      ? []
      : [
          {
            title: "Статус",
            key: "status",
            render: (_: unknown, row: Row) => (
              <Tag color={row.status === "blocked" ? "default" : "green"}>
                {kind === "vehicles"
                  ? vehicleStatuses.find((s) => s.value === row.status)?.label
                  : row.status === "active"
                    ? "Активен"
                    : row.status === "invited"
                      ? "Приглашён"
                      : "Заблокирован"}
              </Tag>
            ),
          },
        ]),
    {
      key: "edit",
      width: 140,
      render: (_, row) => (
        <Button
          icon={<EditOutlined aria-hidden="true" />}
          type="link"
          aria-label={`Редактировать ${row.name}`}
          onClick={() => {
            setEditing(row);
            setOpen(true);
          }}
        >
          Изменить
        </Button>
      ),
    },
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">СПРАВОЧНИКИ КОМПАНИИ</span>
          <h1>{titles[kind][0]}</h1>
          <p>{titles[kind][1]}</p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined aria-hidden="true" />}
          onClick={() => {
            setEditing(null);
            setOpen(true);
          }}
        >
          {titles[kind][2]}
        </Button>
      </div>
      <section className="panel">
        <div className="table-toolbar">
          <div className="table-title">
            <h2>{titles[kind][0]}</h2>
            <Tag>{query.data?.length ?? "…"}</Tag>
          </div>
          <Input
            prefix={<SearchOutlined aria-hidden="true" />}
            placeholder="Поиск по справочнику"
            aria-label="Поиск по справочнику"
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="directory-search"
          />
        </div>
        {query.isError ? (
          <Failure error={query.error} retry={() => void query.refetch()} />
        ) : (
          <Table
            rowKey="key"
            columns={columns}
            loading={query.isPending}
            scroll={{ x: 650 }}
            dataSource={query.data?.filter((row) =>
              `${row.name} ${row.description} ${row.contact}`
                .toLowerCase()
                .includes(search.toLowerCase()),
            )}
            pagination={{ pageSize: 15, showSizeChanger: false }}
            locale={{
              emptyText: search ? "Ничего не найдено" : "Справочник пока пуст",
            }}
          />
        )}
      </section>
      <Modal
        title={editing ? "Изменить запись" : titles[kind][2]}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        okText="Сохранить"
        cancelText="Отмена"
        confirmLoading={save.isPending}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            status: kind === "vehicles" ? "available" : "active",
            capacity_kg: 0,
          }}
          onFinish={(values) => {
            // Скрытые поля формы не отправляются в DTO другого типа справочника.
            if (kind === "clients")
              save.mutate({
                name: values.name,
                phone: values.phone || null,
                email: values.email || null,
              });
            else if (kind === "vehicles")
              save.mutate({
                reg_number: values.reg_number,
                type: values.type,
                model: values.model || null,
                capacity_kg: values.capacity_kg,
                status: values.status,
                // PUT полный: скрытая в этой форме дата ТО не должна стираться.
                last_maintenance:
                  editing && "last_maintenance" in editing.raw
                    ? editing.raw.last_maintenance
                    : null,
              });
            else
              save.mutate(
                editing
                  ? {
                      full_name: values.full_name,
                      phone: values.phone || null,
                      status: values.status,
                    }
                  : {
                      full_name: values.full_name,
                      phone: values.phone || null,
                      email: values.email,
                      password: values.password,
                    },
              );
          }}
        >
          {kind === "vehicles" ? (
            <>
              <Form.Item
                name="reg_number"
                label="Госномер"
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    max: 20,
                    message: "Укажите госномер",
                  },
                ]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="type"
                label="Тип транспорта"
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    max: 50,
                    message: "Укажите тип",
                  },
                ]}
              >
                <Input placeholder="Тент, рефрижератор, фургон" />
              </Form.Item>
              <Form.Item
                name="model"
                label="Марка и модель"
                rules={[{ max: 100 }]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="capacity_kg"
                label="Грузоподъёмность, кг"
                rules={[{ required: true }]}
              >
                <InputNumber
                  min={0}
                  max={2147483647}
                  precision={0}
                  className="full-width"
                />
              </Form.Item>
              <Form.Item name="status" label="Статус">
                <Select options={vehicleStatuses} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                name={kind === "clients" ? "name" : "full_name"}
                label={kind === "clients" ? "Название клиента" : "ФИО водителя"}
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    max: 255,
                    message: "Заполните название или ФИО",
                  },
                ]}
              >
                <Input />
              </Form.Item>
              <Form.Item name="phone" label="Телефон" rules={[{ max: 20 }]}>
                <Input autoComplete="tel" />
              </Form.Item>
              <Form.Item
                name="email"
                label="Email"
                rules={[
                  {
                    required: kind === "drivers" && !editing,
                    type: "email",
                    message: "Укажите корректный email",
                  },
                ]}
              >
                <Input
                  disabled={kind === "drivers" && Boolean(editing)}
                  autoComplete="off"
                />
              </Form.Item>
              {kind === "drivers" &&
                (!editing ? (
                  <Form.Item
                    name="password"
                    label="Начальный пароль"
                    extra="Передайте пароль водителю лично."
                    rules={[
                      {
                        required: true,
                        min: 8,
                        max: 128,
                        message: "От 8 до 128 символов",
                      },
                    ]}
                  >
                    <Input.Password autoComplete="new-password" />
                  </Form.Item>
                ) : (
                  <Form.Item name="status" label="Статус">
                    <Select
                      options={[
                        { value: "active", label: "Активен" },
                        { value: "blocked", label: "Заблокирован" },
                        { value: "invited", label: "Приглашён" },
                      ]}
                    />
                  </Form.Item>
                ))}
            </>
          )}
        </Form>
      </Modal>
    </>
  );
}
