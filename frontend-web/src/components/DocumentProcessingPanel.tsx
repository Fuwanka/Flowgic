/** Локальное распознавание даёт черновик: перенос в заказ требует проверки человеком. */
import { useEffect, useState } from "react";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Collapse,
  Form,
  Input,
  Select,
  Spin,
  Tag,
} from "antd";
import {
  CheckOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmProcessedDocument,
  downloadProcessedDocument,
  getProcessedDocument,
  listOrderDocuments,
  retryProcessedDocument,
  uploadOrderDocument,
} from "../client/sdk.gen";
import type { ProcessingOut } from "../client/types.gen";
import { useAuth, useTenantKey } from "../auth";
import { ApiError, errorMessage, read, saveBlob } from "../lib/api";
import { dateTime } from "../lib/domain";
import { Failure, useMutationError } from "./common";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const DOCUMENT_TYPES = [
  { value: "tn", label: "Транспортная накладная" },
  { value: "ttn", label: "ТТН (1-Т)" },
  { value: "torg12", label: "Товарная накладная (ТОРГ-12)" },
  { value: "upd", label: "УПД" },
  { value: "request", label: "Заявка на перевозку" },
  { value: "other", label: "Другой документ / весовой талон" },
] as const;
type DocumentType = (typeof DOCUMENT_TYPES)[number]["value"];
type UploadType = DocumentType | "auto";
type Confirmation = {
  version: number;
  document_type: DocumentType;
  fields: Record<string, string | null>;
  apply_to_order: boolean;
};

export const DOCUMENT_FIELD_GROUPS = [
  { title: "Документ", fields: [
    ["document_number", "Номер документа"],
    ["document_date", "Дата документа"],
    ["request_number", "Номер заявки"],
    ["supporting_document_number", "Номер сопроводительного документа"],
  ] },
  { title: "Участники и реквизиты", fields: [
    ["sender_name", "Грузоотправитель"],
    ["sender_inn", "ИНН грузоотправителя"],
    ["sender_kpp", "КПП грузоотправителя"],
    ["sender_address", "Адрес грузоотправителя"],
    ["recipient_name", "Грузополучатель"],
    ["recipient_inn", "ИНН грузополучателя"],
    ["recipient_kpp", "КПП грузополучателя"],
    ["recipient_address", "Адрес грузополучателя"],
    ["customer_name", "Заказчик перевозки"],
    ["customer_inn", "ИНН заказчика"],
    ["customer_kpp", "КПП заказчика"],
    ["customer_address", "Адрес заказчика"],
    ["carrier_name", "Перевозчик"],
    ["carrier_inn", "ИНН перевозчика"],
    ["carrier_address", "Адрес перевозчика"],
  ] },
  { title: "Груз", fields: [
    ["cargo_description", "Наименование груза"],
    ["cargo_mass", "Масса груза"],
    ["cargo_mass_unit", "Единица массы (кг / т)"],
    ["package_count", "Количество грузовых мест"],
  ] },
  { title: "Маршрут и сроки", fields: [
    ["loading_address", "Адрес погрузки"],
    ["unloading_address", "Адрес выгрузки"],
    ["planned_pickup_datetime", "Плановые дата и время погрузки"],
    ["planned_delivery_datetime", "Плановые дата и время доставки"],
    ["actual_arrival_datetime", "Фактические дата и время прибытия"],
    ["actual_departure_datetime", "Фактические дата и время убытия"],
  ] },
  { title: "Водитель и транспорт", fields: [
    ["driver_name", "ФИО водителя"],
    ["vehicle_number", "Госномер автомобиля"],
    ["trailer_number", "Госномер прицепа"],
  ] },
  { title: "Стоимость и налоги", fields: [
    ["freight_amount", "Стоимость перевозки"],
    ["cargo_value", "Стоимость товара"],
    ["vat_rate", "Ставка НДС"],
    ["vat_amount", "Сумма НДС"],
    ["currency", "Валюта"],
  ] },
] as const;

const STATUS_LABELS: Record<ProcessingOut["status"], string> = {
  queued: "В очереди",
  processing: "Распознаётся",
  needs_review: "Требует проверки",
  confirmed: "Проверен",
  failed: "Ошибка обработки",
};
const CHANGE_LABELS: Record<string, string> = {
  cargo_type: "Груз", cargo_mass_kg: "Масса, кг", origin: "Погрузка",
  destination: "Выгрузка", agreed_price: "Стоимость перевозки",
};
const isRunning = (status?: ProcessingOut["status"]) =>
  status === "queued" || status === "processing";

/** Проверка браузера нужна для удобства; сервер независимо проверяет содержимое. */
export function validateProcessingUpload(file: Pick<File, "name" | "size" | "type">) {
  if (!file.size) return "Выбран пустой файл.";
  if (file.size > MAX_UPLOAD_BYTES) return "Размер файла превышает 20 МБ.";
  const extensionAllowed = /\.(pdf|jpe?g|png)$/i.test(file.name);
  const mimeAllowed = !file.type || ["application/pdf", "image/jpeg", "image/png"].includes(file.type);
  if (!extensionAllowed || !mimeAllowed) return "Выберите PDF, JPEG или PNG.";
  return null;
}

export function documentFieldValues(fields: Record<string, { value?: string | null }>) {
  return Object.fromEntries(DOCUMENT_FIELD_GROUPS.flatMap((group) =>
    group.fields.map(([id]) => [id, fields[id]?.value ?? ""]),
  ));
}

function DocumentStatus({ status }: { status: ProcessingOut["status"] }) {
  return <Tag color={status === "confirmed" ? "green" : status === "failed" ? "red" : "gold"}>
    {STATUS_LABELS[status]}
  </Tag>;
}

function warningLabel(code: string) {
  const labels: Record<string, string> = {
    manual_review_required: "Сверьте предложенные реквизиты с оригиналом перед подтверждением.",
    rule_scores_are_not_calibrated: "Показатель уверенности служит подсказкой при проверке.",
    low_confidence_ocr_present: "В документе есть плохо читаемые фрагменты.",
    no_readable_text: "Читаемый текст не найден. Попробуйте более чёткий скан.",
    no_fields_extracted: "Не удалось уверенно выделить реквизиты. Заполните их по оригиналу.",
    unsupported_document: "Этот вид документа пока не поддерживается для извлечения реквизитов.",
    document_type_not_recognized: "Тип документа не определён. Выберите его при проверке.",
    vat_exempt_text_present: "Обнаружено «без НДС». Это не означает ставку НДС 0%.",
    ttn_grand_total_includes_possible_charges: "Итог ТТН может включать дополнительные расходы. Стоимость товара проверяется отдельно по товарному разделу.",
  };
  const [kind, field] = code.split(":");
  const name = DOCUMENT_FIELD_GROUPS.flatMap((group) => group.fields.map(([id, label]) => ({ id, label }))).find((item) => item.id === field)?.label ?? "Поле";
  if (kind === "conflicting_values") return `${name}: найдены разные значения. Выберите верное по оригиналу.`;
  if (kind === "ocr_organization_zero_confusion") return `${name}: в названии могут быть перепутаны буква О и цифра 0.`;
  if (kind === "inn_checksum_failed") return `${name}: контрольная сумма ИНН не сходится. Проверьте цифры.`;
  if (kind === "negative_value_requires_review") return `${name}: обнаружен знак минус. Проверьте значение по оригиналу.`;
  return labels[code] ?? "Обнаружен неоднозначный фрагмент. Проверьте реквизиты по оригиналу.";
}

/** Временный URL хранится только в этом экземпляре и освобождается при смене записи. */
function OriginalPreview({ document }: { document: ProcessingOut }) {
  const [shown, setShown] = useState(false);
  const [reload, setReload] = useState(0);
  const [preview, setPreview] = useState<{ url: string; blob: Blob } | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!shown) return;
    const controller = new AbortController();
    let alive = true;
    let url: string | undefined;
    setPreview(null);
    setError(null);
    void read(downloadProcessedDocument({
      path: { document_id: document.id }, signal: controller.signal, parseAs: "blob",
    })).then((blob) => {
      if (!alive) return;
      url = URL.createObjectURL(blob);
      setPreview({ url, blob });
    }).catch((cause: unknown) => {
      if (alive) setError(cause);
    });
    return () => {
      alive = false;
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [shown, reload, document.id]);
  const isPdf = preview?.blob.type === "application/pdf";
  return <div className="ocr-original">
    <Button onClick={() => setShown((value) => !value)} aria-expanded={shown}>
      {shown ? "Скрыть оригинал" : "Открыть оригинал для сверки"}
    </Button>
    {shown && <div className="ocr-preview">
      {error ? <Alert type="warning" title="Не удалось открыть оригинал" description={errorMessage(error)}
        action={<Button onClick={() => setReload((value) => value + 1)}>Повторить</Button>} /> :
        preview ? <>
          <Button icon={<DownloadOutlined aria-hidden="true" />} onClick={() => saveBlob(preview.blob, document.original_filename)}>
            Скачать оригинал
          </Button>
          {isPdf ? <object data={preview.url} type="application/pdf" aria-label={`Оригинал ${document.original_filename}`}>
            <p>Предпросмотр PDF недоступен в этом браузере. Скачайте оригинал для сверки.</p>
          </object> : <img src={preview.url} alt={`Оригинал документа ${document.original_filename}`} />}
        </> : <div role="status" className="ocr-preview-loading"><Spin /> Загрузка оригинала…</div>}
    </div>}
  </div>;
}

function ReviewForm({ document, saving, onConfirm }: {
  document: ProcessingOut;
  saving: boolean;
  onConfirm: (body: Confirmation) => void;
}) {
  const [form] = Form.useForm();
  const [sources, setSources] = useState(false);
  const [apply, setApply] = useState(false);
  const initialType = DOCUMENT_TYPES.some((type) => type.value === document.document_type)
    ? document.document_type as DocumentType : "other";
  const selectedType: DocumentType = Form.useWatch("document_type", form) ?? initialType;
  const canApply = ["tn", "ttn", "request"].includes(selectedType);
  const readOnly = document.status === "confirmed";
  return <Form form={form} layout="vertical" disabled={saving || readOnly}
    initialValues={{ document_type: initialType, fields: documentFieldValues(document.fields) }}
    onFinish={(values: { document_type: DocumentType; fields: Record<string, string> }) => {
      onConfirm({ version: document.version, document_type: values.document_type,
        fields: Object.fromEntries(Object.entries(values.fields).map(([id, value]) => [id, value.trim() || null])),
        apply_to_order: canApply && apply,
      });
    }}>
    <Form.Item name="document_type" label="Тип документа после проверки">
      <Select options={[...DOCUMENT_TYPES]} onChange={() => setApply(false)} />
    </Form.Item>
    <Checkbox checked={sources} disabled={false} onChange={(event) => setSources(event.target.checked)}>
      Показывать исходный текст и страницы для каждого поля
    </Checkbox>
    <p className="muted ocr-advisory">Уверенность OCR помогает найти ошибки, но не подтверждает достоверность. Сверьте значения с оригиналом; пустые поля можно заполнить вручную.</p>
    <Collapse className="ocr-field-groups" defaultActiveKey={["Документ", "Груз", "Маршрут и сроки"]}
      items={DOCUMENT_FIELD_GROUPS.map((group) => ({ key: group.title, label: group.title,
        forceRender: true,
        children: <div className="ocr-fields">{group.fields.map(([id, label]) => {
          const extracted = document.fields[id];
          return <div className={extracted?.review_required ? "ocr-field ocr-field-review" : "ocr-field"} key={id}>
            <Form.Item name={["fields", id]} label={label}>
              <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} maxLength={2000} placeholder="Не найдено — можно заполнить" />
            </Form.Item>
            {extracted?.confidence !== null && extracted?.confidence !== undefined && <small className="muted">
              Уверенность OCR: {Math.round(extracted.confidence * 100)}%
            </small>}
            {extracted?.review_required && <Tag color="orange">Сверить с оригиналом</Tag>}
            {sources && <div className="ocr-source">
              {extracted?.raw_text && <p><strong>Исходный текст:</strong> <mark>{extracted.raw_text}</mark></p>}
              {extracted?.evidence?.length ? extracted.evidence.map((evidence, index) => <p key={index}>
                <strong>Страница {evidence.page}:</strong> <mark>{evidence.text}</mark>
                <span className="ocr-source-box">Область (% страницы: x, y, ширина, высота): {evidence.bbox.map((value) => Math.round(value * 10) / 10).join(", ")}</span>
              </p>) : <span>Привязка к странице не найдена.</span>}
            </div>}
          </div>;
        })}</div>,
      }))} />
    {Object.keys(document.order_changes).length > 0 && <div className="ocr-order-changes">
      <h3>Предложенные изменения заказа</h3>
      <p className="muted">Предложение по результату распознавания, до ваших правок. Сверьте эти значения и исправленные поля перед переносом.</p>
      <dl>{Object.entries(document.order_changes).map(([field, change]) => <div key={field}>
        <dt>{CHANGE_LABELS[field] ?? field}</dt>
        <dd><span>{change.current || "Не указано"}</span><span aria-hidden="true"> → </span><strong>{change.proposed || "Не указано"}</strong></dd>
      </div>)}</dl>
    </div>}
    {readOnly ? <Alert type="success" title="Проверка документа сохранена"
      description={document.confirmed_at ? `Подтверждён ${dateTime(document.confirmed_at)}.` : undefined} /> : <>
      <div className="ocr-confirm">
        <Checkbox checked={apply} disabled={!canApply || saving} onChange={(event) => setApply(event.target.checked)}>
          Также перенести проверенные данные в заказ
        </Checkbox>
        <p className="muted">Для ТН, ТТН и заявки можно обновить груз, массу, адреса погрузки и выгрузки, согласованную стоимость перевозки. Стоимость товара не становится стоимостью рейса. Финансовый расчёт, статус и назначение водителя не изменяются.</p>
        {!canApply && <p className="muted">Для выбранного типа сохраняются только проверенные поля документа.</p>}
      </div>
      <Button type="primary" htmlType="submit" icon={<CheckOutlined aria-hidden="true" />} loading={saving}>
        {apply && canApply ? "Подтвердить и обновить заказ" : "Сохранить проверку документа"}
      </Button>
    </>}
  </Form>;
}

function ProcessingPanel({ orderId }: { orderId: string }) {
  const tenantKey = useTenantKey();
  const { user } = useAuth();
  const cache = useQueryClient();
  const { message } = App.useApp();
  const mutationError = useMutationError();
  const documentKey = [...tenantKey, "processed-documents", user!.id, orderId];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploadType, setUploadType] = useState<UploadType>("auto");
  const [uploadKey, setUploadKey] = useState<string | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [fileError, setFileError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const documents = useQuery({
    queryKey: documentKey,
    queryFn: ({ signal }) => read(listOrderDocuments({ path: { order_id: orderId }, signal })),
    refetchInterval: (query) => query.state.data?.items.some((item) => isRunning(item.status)) ? 2500 : false,
  });
  const selected = documents.data?.items.find((item) => item.id === selectedId) ?? documents.data?.items[0];
  const detailsKey = [...documentKey, "detail", selected?.id];
  const detail = useQuery({
    queryKey: detailsKey,
    enabled: Boolean(selected),
    queryFn: ({ signal }) => read(getProcessedDocument({ path: { document_id: selected!.id }, signal })),
    refetchInterval: (query) => isRunning(query.state.data?.status ?? selected?.status) ? 2500 : false,
  });
  const current = detail.data ?? selected;
  const refreshDocuments = () => cache.invalidateQueries({ queryKey: documentKey });
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.status === 409) {
      setStale(true);
      void refreshDocuments();
    } else mutationError(error);
  };
  const upload = useMutation({
    mutationFn: ({ file: selectedFile, type, uploadKey: key }: { file: File; type: UploadType; uploadKey: string }) =>
      read(uploadOrderDocument({ path: { order_id: orderId }, body: { file: selectedFile, document_type: type, upload_key: key } })),
    onError,
    onSuccess: async (document) => {
      setSelectedId(document.id);
      setFile(null);
      setUploadKey(null);
      setInputKey((value) => value + 1);
      setStale(false);
      await refreshDocuments();
      void message.success("Документ принят в обработку");
    },
  });
  const retry = useMutation({
    mutationFn: (documentId: string) => read(retryProcessedDocument({ path: { document_id: documentId } })),
    onError,
    onSuccess: async (document) => {
      cache.setQueryData([...documentKey, "detail", document.id], document);
      await refreshDocuments();
    },
  });
  const confirm = useMutation({
    mutationFn: (body: Confirmation) =>
      read(confirmProcessedDocument({ path: { document_id: current!.id }, body })),
    onError,
    onSuccess: async (document) => {
      cache.setQueryData([...documentKey, "detail", document.id], document);
      setStale(false);
      await Promise.all([
        refreshDocuments(),
        cache.invalidateQueries({ queryKey: [...tenantKey, "order", orderId] }),
        cache.invalidateQueries({ queryKey: [...tenantKey, "orders"] }),
      ]);
      void message.success("Проверенные данные сохранены");
    },
  });
  return <section className="panel detail-panel ocr-panel" aria-labelledby="ocr-heading">
    <div className="section-heading">
      <h2 id="ocr-heading"><FileSearchOutlined aria-hidden="true" /> Распознавание накладных</h2>
      <Button icon={<ReloadOutlined aria-hidden="true" />} onClick={() => void refreshDocuments()} loading={documents.isFetching}>Обновить</Button>
    </div>
    <p className="muted">Загрузите российскую ТН, ТТН, ТОРГ-12, УПД, заявку или весовой талон. Результат распознавания сохраняется как черновик для вашей проверки.</p>
    <div className="ocr-upload">
      <div>
        <label htmlFor="ocr-upload-type">Тип загружаемого документа</label>
        <Select id="ocr-upload-type" aria-label="Тип загружаемого документа" className="full-width"
          value={uploadType} disabled={upload.isPending} options={[{ value: "auto", label: "Определить автоматически" }, ...DOCUMENT_TYPES]}
          onChange={(value: UploadType) => { setUploadType(value); setUploadKey(null); }} />
      </div>
      <div>
        <label htmlFor="ocr-upload-file">Оригинал (PDF, JPEG, PNG · до 20 МБ)</label>
        <input key={inputKey} id="ocr-upload-file" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          disabled={upload.isPending} aria-describedby={fileError ? "ocr-file-error" : undefined}
          onChange={(event) => {
            const chosen = event.target.files?.[0] ?? null;
            const validation = chosen ? validateProcessingUpload(chosen) : null;
            setFileError(validation); setFile(validation ? null : chosen); setUploadKey(null);
          }} />
      </div>
      <Button type="primary" icon={<UploadOutlined aria-hidden="true" />} loading={upload.isPending} disabled={!file}
        onClick={() => {
          if (!file) return;
          const attemptKey = uploadKey ?? crypto.randomUUID();
          setUploadKey(attemptKey);
          upload.mutate({ file, type: uploadType, uploadKey: attemptKey });
        }}>Распознать</Button>
    </div>
    {fileError && <p id="ocr-file-error" role="alert" className="ocr-error">{fileError}</p>}
    {documents.isPending ? <div className="ocr-preview-loading" role="status"><Spin /> Загрузка документов…</div> :
      documents.isError ? <Failure error={documents.error} retry={() => void documents.refetch()} /> :
        !documents.data.items.length ? <p className="ocr-empty">Прикреплённых документов пока нет. После загрузки здесь появятся оригинал и поля для сверки.</p> : <>
          <div className="ocr-document-list" aria-label="Документы заказа">
            {documents.data.items.map((document) => <button type="button" key={document.id}
              className={`ocr-document ${current?.id === document.id ? "ocr-document-selected" : ""}`}
              aria-pressed={current?.id === document.id} disabled={confirm.isPending || retry.isPending}
              onClick={() => { setSelectedId(document.id); setStale(false); }}>
              <strong>{document.original_filename}</strong>
              <span><DocumentStatus status={document.status} /> {dateTime(document.created_at)}</span>
            </button>)}
          </div>
          {detail.isError && <Alert type="warning" title="Не удалось обновить документ" description={errorMessage(detail.error)}
            action={<Button onClick={() => void detail.refetch()}>Повторить</Button>} />}
          {current && <div className="ocr-review" key={current.id}>
            <div className="section-heading"><h3>{current.original_filename}</h3><DocumentStatus status={current.status} /></div>
            <OriginalPreview document={current} />
            {stale && <Alert type="warning" title={detail.isFetching
              ? "Документ уже изменён в другой вкладке. Загружаем актуальную версию."
              : "Документ уже изменён в другой вкладке. Повторно проверьте обновлённые поля перед сохранением."} />}
            {current.warnings.length > 0 && <Alert type="warning" title="Обратите внимание" description={<ul>{current.warnings.map((warning, index) => <li key={index}>{warningLabel(warning)}</li>)}</ul>} />}
            {isRunning(current.status) ? <div role="status" className="ocr-preview-loading"><Spin /> {current.status === "queued" ? "Документ ожидает обработки. Статус обновится автоматически." : "Распознаём документ. Можно продолжать работу с заказом."}
              {Date.now() - Date.parse(current.updated_at) > 15 * 60 * 1000 && <Button loading={retry.isPending} onClick={() => retry.mutate(current.id)}>Повторить зависшую обработку</Button>}
            </div> :
              current.status === "failed" ? <Alert type="error" title="Документ не обработан" description={current.error || "Не удалось распознать документ. Попробуйте повторить обработку или загрузите более чёткий оригинал."}
                action={<Button loading={retry.isPending} onClick={() => retry.mutate(current.id)}>Повторить обработку</Button>} /> :
                <ReviewForm key={`${current.id}:${current.version}`} document={current} saving={confirm.isPending || (stale && (detail.isFetching || detail.isError))} onConfirm={(body) => confirm.mutate(body)} />}
          </div>}
        </>}
  </section>;
}

export function DocumentProcessingPanel({ orderId }: { orderId: string }) {
  const { user } = useAuth();
  // Идентичность включает пользователя: смена аккаунта уничтожает черновик и Blob URL.
  return user ? <ProcessingPanel key={`${user.company.id_company}:${user.id}:${orderId}`} orderId={orderId} /> : null;
}
