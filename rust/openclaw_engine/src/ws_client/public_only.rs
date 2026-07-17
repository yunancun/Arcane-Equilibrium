//! Immutable Bybit public market-data transport for the reduced engine profile.

use futures_util::{Sink, SinkExt, StreamExt};
use openclaw_types::{PriceEvent, PriceEventKind};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

use super::run_loop::{
    BACKOFF_POLICY, PUBLIC_MARKET_DATA_ONLY_ENDPOINT, PUBLIC_MARKET_DATA_ONLY_HEARTBEAT,
    PUBLIC_MARKET_DATA_ONLY_RECONNECT_BASE_MS, PUBLIC_MARKET_DATA_ONLY_TOPICS,
};

const PUBLIC_MARKET_DATA_ONLY_SEND_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Debug)]
enum PublicSendOutcome<E> {
    Sent,
    Cancelled,
    TimedOut,
    Failed(E),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum EventDeliveryOutcome {
    Delivered,
    Cancelled,
    DrainClosed,
}

async fn send_cancel_bounded<S>(
    sink: &mut S,
    message: Message,
    cancel: &CancellationToken,
    max_wait: Duration,
) -> PublicSendOutcome<S::Error>
where
    S: Sink<Message> + Unpin,
{
    tokio::select! {
        biased;
        _ = cancel.cancelled() => PublicSendOutcome::Cancelled,
        result = tokio::time::timeout(max_wait, sink.send(message)) => match result {
            Ok(Ok(())) => PublicSendOutcome::Sent,
            Ok(Err(error)) => PublicSendOutcome::Failed(error),
            Err(_) => PublicSendOutcome::TimedOut,
        },
    }
}

async fn deliver_event_cancel_aware(
    event_tx: &mpsc::Sender<PriceEvent>,
    event: PriceEvent,
    cancel: &CancellationToken,
) -> EventDeliveryOutcome {
    tokio::select! {
        biased;
        _ = cancel.cancelled() => EventDeliveryOutcome::Cancelled,
        result = event_tx.send(event) => match result {
            Ok(()) => EventDeliveryOutcome::Delivered,
            Err(_) if cancel.is_cancelled() => EventDeliveryOutcome::Cancelled,
            Err(_) => EventDeliveryOutcome::DrainClosed,
        },
    }
}

#[derive(Debug, thiserror::Error)]
pub enum PublicMarketDataOnlyWsError {
    #[error("public market-data drain channel closed")]
    DrainClosed,
}

pub struct PublicMarketDataOnlyWsClient {
    event_tx: mpsc::Sender<PriceEvent>,
    cancel: CancellationToken,
}

impl PublicMarketDataOnlyWsClient {
    pub fn new(event_tx: mpsc::Sender<PriceEvent>, cancel: CancellationToken) -> Self {
        Self { event_tx, cancel }
    }

    pub async fn run(self) -> Result<(), PublicMarketDataOnlyWsError> {
        let mut attempt = 0_u32;
        loop {
            if self.cancel.is_cancelled() {
                return Ok(());
            }

            let connected = tokio::select! {
                _ = self.cancel.cancelled() => return Ok(()),
                result = tokio::time::timeout(
                    Duration::from_secs(15),
                    tokio_tungstenite::connect_async(PUBLIC_MARKET_DATA_ONLY_ENDPOINT),
                ) => result,
            };

            match connected {
                Ok(Ok((stream, _response))) => {
                    attempt = 0;
                    let (mut write, mut read) = stream.split();
                    let subscribe = serde_json::json!({
                        "op": "subscribe",
                        "args": PUBLIC_MARKET_DATA_ONLY_TOPICS,
                    });
                    match send_cancel_bounded(
                        &mut write,
                        Message::Text(subscribe.to_string().into()),
                        &self.cancel,
                        PUBLIC_MARKET_DATA_ONLY_SEND_TIMEOUT,
                    )
                    .await
                    {
                        PublicSendOutcome::Cancelled => return Ok(()),
                        PublicSendOutcome::TimedOut => {
                            warn!("public market-data subscribe timed out");
                        }
                        PublicSendOutcome::Failed(error) => {
                            warn!(%error, "public market-data subscribe failed");
                        }
                        PublicSendOutcome::Sent => {
                            info!(
                                endpoint = PUBLIC_MARKET_DATA_ONLY_ENDPOINT,
                                topics = PUBLIC_MARKET_DATA_ONLY_TOPICS.len(),
                                "public market-data transport connected"
                            );
                            let mut heartbeat =
                                tokio::time::interval(PUBLIC_MARKET_DATA_ONLY_HEARTBEAT);
                            heartbeat.tick().await;

                            'connection: loop {
                                tokio::select! {
                                    _ = self.cancel.cancelled() => return Ok(()),
                                    _ = heartbeat.tick() => {
                                        let ping = serde_json::json!({"op": "ping"});
                                        match send_cancel_bounded(
                                            &mut write,
                                            Message::Text(ping.to_string().into()),
                                            &self.cancel,
                                            PUBLIC_MARKET_DATA_ONLY_SEND_TIMEOUT,
                                        ).await {
                                            PublicSendOutcome::Sent => {}
                                            PublicSendOutcome::Cancelled => return Ok(()),
                                            PublicSendOutcome::TimedOut => {
                                                warn!("public market-data heartbeat timed out");
                                                break 'connection;
                                            }
                                            PublicSendOutcome::Failed(error) => {
                                                warn!(%error, "public market-data heartbeat failed");
                                                break 'connection;
                                            }
                                        }
                                    }
                                    message = read.next() => {
                                        match message {
                                            Some(Ok(Message::Text(text))) => {
                                                for event in parse_fixed_public_message(text.as_str()) {
                                                    match deliver_event_cancel_aware(
                                                        &self.event_tx,
                                                        event,
                                                        &self.cancel,
                                                    )
                                                    .await
                                                    {
                                                        EventDeliveryOutcome::Delivered => {}
                                                        EventDeliveryOutcome::Cancelled => return Ok(()),
                                                        EventDeliveryOutcome::DrainClosed => {
                                                            return Err(PublicMarketDataOnlyWsError::DrainClosed);
                                                        }
                                                    }
                                                }
                                            }
                                            Some(Ok(Message::Ping(data))) => {
                                                match send_cancel_bounded(
                                                    &mut write,
                                                    Message::Pong(data),
                                                    &self.cancel,
                                                    PUBLIC_MARKET_DATA_ONLY_SEND_TIMEOUT,
                                                ).await {
                                                    PublicSendOutcome::Sent => {}
                                                    PublicSendOutcome::Cancelled => return Ok(()),
                                                    PublicSendOutcome::TimedOut => {
                                                        warn!("public market-data pong timed out");
                                                        break 'connection;
                                                    }
                                                    PublicSendOutcome::Failed(error) => {
                                                        warn!(%error, "public market-data pong failed");
                                                        break 'connection;
                                                    }
                                                }
                                            }
                                            Some(Ok(Message::Close(_))) | None => break 'connection,
                                            Some(Err(error)) => {
                                                warn!(%error, "public market-data read failed");
                                                break 'connection;
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(Err(error)) => warn!(%error, "public market-data connect failed"),
                Err(_) => warn!("public market-data connect timed out"),
            }

            attempt = attempt.saturating_add(1);
            let delay = BACKOFF_POLICY
                .next_delay_with_base(PUBLIC_MARKET_DATA_ONLY_RECONNECT_BASE_MS, attempt);
            debug!(
                attempt,
                delay_ms = delay.as_millis(),
                "public market-data reconnect wait"
            );
            tokio::select! {
                _ = self.cancel.cancelled() => return Ok(()),
                _ = tokio::time::sleep(delay) => {}
            }
        }
    }

    pub const fn endpoint() -> &'static str {
        PUBLIC_MARKET_DATA_ONLY_ENDPOINT
    }

    pub const fn topics() -> &'static [&'static str] {
        &PUBLIC_MARKET_DATA_ONLY_TOPICS
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn parse_fixed_public_message(text: &str) -> Vec<PriceEvent> {
    let parsed: serde_json::Value = match serde_json::from_str(text) {
        Ok(parsed) => parsed,
        Err(_) => return Vec::new(),
    };
    if parsed.get("op").is_some() || parsed.get("success").is_some() {
        return Vec::new();
    }
    let Some(topic) = parsed.get("topic").and_then(serde_json::Value::as_str) else {
        return Vec::new();
    };
    if !PUBLIC_MARKET_DATA_ONLY_TOPICS.contains(&topic) {
        return Vec::new();
    }
    let Some(items) = parsed.get("data").and_then(serde_json::Value::as_array) else {
        return Vec::new();
    };

    if let Some(symbol) = topic.strip_prefix("publicTrade.") {
        return items
            .iter()
            .filter_map(|item| parse_trade(item, symbol))
            .collect();
    }
    let Some(symbol) = topic.strip_prefix("kline.1.") else {
        return Vec::new();
    };
    items
        .iter()
        .filter_map(|item| parse_kline(item, symbol))
        .collect()
}

fn parse_number(item: &serde_json::Value, key: &str) -> Option<f64> {
    item.get(key)
        .and_then(serde_json::Value::as_str)
        .and_then(|raw| raw.parse::<f64>().ok())
        .filter(|value| value.is_finite())
}

fn parse_u64(item: &serde_json::Value, key: &str) -> Option<u64> {
    item.get(key).and_then(|value| {
        value
            .as_u64()
            .or_else(|| value.as_str().and_then(|raw| raw.parse().ok()))
    })
}

fn payload_symbol_matches(item: &serde_json::Value, expected: &str) -> bool {
    item.get("s")
        .and_then(serde_json::Value::as_str)
        .map(|symbol| symbol == expected)
        .unwrap_or(true)
}

fn parse_trade(item: &serde_json::Value, symbol: &str) -> Option<PriceEvent> {
    if !payload_symbol_matches(item, symbol) {
        return None;
    }
    let mut event = PriceEvent::new(
        symbol.to_string(),
        parse_number(item, "p")?,
        parse_u64(item, "T").unwrap_or_else(now_ms),
    );
    event.event_kind = Some(PriceEventKind::Trade);
    event.trade_qty = parse_number(item, "v");
    event.trade_side = item
        .get("S")
        .and_then(serde_json::Value::as_str)
        .map(ToOwned::to_owned);
    Some(event)
}

fn parse_kline(item: &serde_json::Value, symbol: &str) -> Option<PriceEvent> {
    if !payload_symbol_matches(item, symbol) {
        return None;
    }
    let mut event = PriceEvent::new(
        symbol.to_string(),
        parse_number(item, "close")?,
        parse_u64(item, "start").unwrap_or_else(now_ms),
    );
    event.volume_24h = parse_number(item, "volume").unwrap_or(0.0);
    Some(event)
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::Sink;
    use std::{
        pin::Pin,
        task::{Context, Poll},
    };

    struct PendingSink;

    #[derive(Default)]
    struct ReadySink {
        sent: bool,
    }

    impl Sink<Message> for PendingSink {
        type Error = tokio_tungstenite::tungstenite::Error;

        fn poll_ready(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            Poll::Pending
        }

        fn start_send(self: Pin<&mut Self>, _item: Message) -> Result<(), Self::Error> {
            panic!("a permanently pending sink must never accept a message")
        }

        fn poll_flush(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            Poll::Pending
        }

        fn poll_close(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            Poll::Pending
        }
    }

    impl Sink<Message> for ReadySink {
        type Error = tokio_tungstenite::tungstenite::Error;

        fn poll_ready(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            Poll::Ready(Ok(()))
        }

        fn start_send(mut self: Pin<&mut Self>, _item: Message) -> Result<(), Self::Error> {
            self.sent = true;
            Ok(())
        }

        fn poll_flush(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            Poll::Ready(Ok(()))
        }

        fn poll_close(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            Poll::Ready(Ok(()))
        }
    }

    #[test]
    fn fixed_parser_accepts_only_the_compiled_topic_set() {
        let denied = r#"{"topic":"publicTrade.SOLUSDT","data":[{"s":"SOLUSDT","p":"1"}]}"#;
        assert!(parse_fixed_public_message(denied).is_empty());
        let allowed = r#"{"topic":"publicTrade.BTCUSDT","data":[{"s":"BTCUSDT","p":"60000","v":"0.1","T":42,"S":"Buy"}]}"#;
        let events = parse_fixed_public_message(allowed);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].symbol, "BTCUSDT");
        assert_eq!(events[0].last_price, 60_000.0);
        assert_eq!(events[0].ts_ms, 42);
    }

    #[tokio::test]
    async fn pending_sink_send_is_cancelled_without_waiting_for_send_timeout() {
        let cancel = CancellationToken::new();
        let cancel_trigger = cancel.clone();
        let task = tokio::spawn(async move {
            let mut sink = PendingSink;
            send_cancel_bounded(
                &mut sink,
                Message::Text("pending".into()),
                &cancel,
                Duration::from_secs(60),
            )
            .await
        });

        tokio::task::yield_now().await;
        cancel_trigger.cancel();
        let outcome = tokio::time::timeout(Duration::from_millis(250), task)
            .await
            .expect("cancellation must finish the pending send")
            .expect("pending-send task must join cleanly");

        assert!(matches!(outcome, PublicSendOutcome::Cancelled));
    }

    #[tokio::test]
    async fn cancellation_wins_when_sink_send_is_also_ready() {
        let cancel = CancellationToken::new();
        cancel.cancel();
        let mut sink = ReadySink::default();

        let outcome = send_cancel_bounded(
            &mut sink,
            Message::Text("must-not-send".into()),
            &cancel,
            Duration::from_secs(1),
        )
        .await;

        assert!(matches!(outcome, PublicSendOutcome::Cancelled));
        assert!(!sink.sent);
    }

    #[tokio::test]
    async fn pending_sink_send_is_bounded_without_cancellation() {
        let cancel = CancellationToken::new();
        let mut sink = PendingSink;

        let outcome = send_cancel_bounded(
            &mut sink,
            Message::Text("pending".into()),
            &cancel,
            Duration::from_millis(5),
        )
        .await;

        assert!(matches!(outcome, PublicSendOutcome::TimedOut));
    }

    #[tokio::test]
    async fn receiver_drop_and_cancel_race_resolves_as_clean_cancellation() {
        let (event_tx, event_rx) = mpsc::channel(1);
        let cancel = CancellationToken::new();
        drop(event_rx);
        cancel.cancel();

        let outcome = deliver_event_cancel_aware(
            &event_tx,
            PriceEvent::new("BTCUSDT".to_string(), 60_000.0, 42),
            &cancel,
        )
        .await;

        assert!(matches!(outcome, EventDeliveryOutcome::Cancelled));
    }

    #[tokio::test]
    async fn receiver_drop_without_cancellation_remains_drain_closed() {
        let (event_tx, event_rx) = mpsc::channel(1);
        let cancel = CancellationToken::new();
        drop(event_rx);

        let outcome = deliver_event_cancel_aware(
            &event_tx,
            PriceEvent::new("BTCUSDT".to_string(), 60_000.0, 42),
            &cancel,
        )
        .await;

        assert!(matches!(outcome, EventDeliveryOutcome::DrainClosed));
    }
}
