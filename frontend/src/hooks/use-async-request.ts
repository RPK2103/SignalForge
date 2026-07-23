"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  SignalForgeApiError,
  formatApiErrorMessage,
} from "@/lib/api/errors";
import { useMountedRef } from "@/hooks/use-mounted";

export type AsyncStatus = "idle" | "loading" | "success" | "error";

export type AsyncState<T> = {
  status: AsyncStatus;
  data: T | null;
  error: SignalForgeApiError | null;
  errorMessage: string | null;
};

export function useAsyncRequest<T>() {
  const mountedRef = useMountedRef();
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const [state, setState] = useState<AsyncState<T>>({
    status: "idle",
    data: null,
    error: null,
    errorMessage: null,
  });

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const execute = useCallback(
    async (runner: (signal: AbortSignal) => Promise<T>) => {
      cancel();
      const controller = new AbortController();
      abortRef.current = controller;
      const requestId = ++requestIdRef.current;

      if (mountedRef.current) {
        setState((prev) => ({
          ...prev,
          status: "loading",
          error: null,
          errorMessage: null,
        }));
      }

      try {
        const data = await runner(controller.signal);
        if (!mountedRef.current || requestId !== requestIdRef.current) {
          return null;
        }
        setState({
          status: "success",
          data,
          error: null,
          errorMessage: null,
        });
        return data;
      } catch (error) {
        if (!mountedRef.current || requestId !== requestIdRef.current) {
          return null;
        }

        const apiError =
          error instanceof SignalForgeApiError
            ? error
            : new SignalForgeApiError({
                message: "Unexpected error",
                category: "unknown_error",
                cause: error,
              });

        setState({
          status: "error",
          data: null,
          error: apiError,
          errorMessage: formatApiErrorMessage(apiError),
        });
        return null;
      }
    },
    [cancel, mountedRef]
  );

  useEffect(() => cancel, [cancel]);

  return { state, execute, cancel, setState };
}
