/** Офферы приходят с сервера для текущего контекста; переход фиксируется до открытия URL. */
import { App, Button, Tag } from "antd";
import { ExportOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { getContextualOffers, recordOfferClick } from "../client/sdk.gen";
import { read, errorMessage } from "../lib/api";
import { useTenantKey } from "../auth";

export function OfferPanel({ orderId }: { orderId?: string }) {
  const key = useTenantKey();
  const { message } = App.useApp();
  const query = useQuery({
    queryKey: [...key, "offers", orderId],
    queryFn: () =>
      read(
        getContextualOffers({
          query: {
            context_type: orderId ? "order_detail" : "dashboard",
            order_id: orderId,
          },
        }),
      ),
  });
  if (query.isError)
    return (
      <div className="muted">
        Предложения временно недоступны.{" "}
        <Button type="link" onClick={() => void query.refetch()}>
          Повторить
        </Button>
      </div>
    );
  if (!query.data?.length) return null;
  return (
    <section className="offers-section" aria-label="Партнёрские предложения">
      <div className="section-heading">
        <h2>
          <SafetyCertificateOutlined aria-hidden="true" /> Для вашей перевозки
        </h2>
        <span>Партнёрские предложения</span>
      </div>
      <div className="offers-grid">
        {query.data.map((offer) => (
          <article className="offer-card" key={offer.id}>
            <Tag color="cyan">
              {offer.is_demo ? "Демо-предложение" : "Партнёр Flowgic"}
            </Tag>
            <h3>{offer.title}</h3>
            <p>{offer.description}</p>
            <Button
              type="link"
              icon={<ExportOutlined aria-hidden="true" />}
              onClick={async () => {
                const tab = window.open("about:blank", "_blank");
                if (tab) tab.opener = null;
                try {
                  const click = await read(
                    recordOfferClick({
                      path: { offer_id: offer.id },
                      body: { order_id: orderId },
                    }),
                  );
                  const url = new URL(click.target_url);
                  if (!["http:", "https:"].includes(url.protocol))
                    throw new Error("Недопустимая ссылка предложения");
                  if (tab) tab.location.href = url.href;
                  else window.location.assign(url.href);
                } catch (error) {
                  tab?.close();
                  void message.error(errorMessage(error));
                }
              }}
            >
              Подробнее
            </Button>
          </article>
        ))}
      </div>
    </section>
  );
}
