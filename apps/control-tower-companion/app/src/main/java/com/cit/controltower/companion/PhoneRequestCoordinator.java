package com.cit.controltower.companion;

import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

final class PhoneRequestCoordinator {
    private static final ConcurrentHashMap<String, Object> LOCKS = new ConcurrentHashMap<>();

    private PhoneRequestCoordinator() {
    }

    static <T> T run(String deviceId, Supplier<T> request) {
        // Sequence allocation and delivery share one lock across local and remote clients.
        synchronized (LOCKS.computeIfAbsent(deviceId, ignored -> new Object())) {
            return request.get();
        }
    }
}
