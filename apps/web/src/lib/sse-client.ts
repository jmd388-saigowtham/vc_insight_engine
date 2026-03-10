const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SSEOptions<T> {
  url: string;
  onEvent: (data: T) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export function createEventSource<T>(options: SSEOptions<T>) {
  const { url, onEvent, onError, onOpen, onClose } = options;
  const fullUrl = `${BASE_URL}${url}`;
  let eventSource: EventSource | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let lastEventId = "";
  let closed = false;

  function connect() {
    if (closed) return;

    const connectUrl = lastEventId
      ? `${fullUrl}${fullUrl.includes("?") ? "&" : "?"}lastEventId=${lastEventId}`
      : fullUrl;

    eventSource = new EventSource(connectUrl);

    eventSource.onopen = () => {
      onOpen?.();
    };

    // Listen for named "trace" events from the backend
    eventSource.addEventListener("trace", (event: MessageEvent) => {
      if (event.lastEventId) {
        lastEventId = event.lastEventId;
      }
      try {
        const data = JSON.parse(event.data) as T;
        onEvent(data);
      } catch {
        // non-JSON data, ignore
      }
    });

    // Also handle generic messages (fallback)
    eventSource.onmessage = (event) => {
      if (event.lastEventId) {
        lastEventId = event.lastEventId;
      }
      try {
        const data = JSON.parse(event.data) as T;
        onEvent(data);
      } catch {
        // non-JSON data, ignore
      }
    };

    eventSource.onerror = (event) => {
      onError?.(event);
      eventSource?.close();

      if (!closed) {
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };
  }

  connect();

  return {
    close() {
      closed = true;
      eventSource?.close();
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      onClose?.();
    },
  };
}
