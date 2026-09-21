package com.cit.controltower.companion;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class PhoneRequestCoordinatorTest {
    @Test
    public void sharedIdentityRequestsStayOrderedWhileOtherSitesCanFinish() throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(3);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        List<String> completed = Collections.synchronizedList(new ArrayList<>());
        try {
            Future<?> first = workers.submit(() -> PhoneRequestCoordinator.run("academy", () -> {
                firstStarted.countDown();
                try {
                    if (!releaseFirst.await(5, TimeUnit.SECONDS)) {
                        throw new AssertionError("Test did not release the first request");
                    }
                } catch (InterruptedException error) {
                    throw new AssertionError(error);
                }
                completed.add("unlock-1");
                return null;
            }));
            assertTrue(firstStarted.await(2, TimeUnit.SECONDS));
            Future<?> second = workers.submit(() -> {
                secondStarted.countDown();
                return PhoneRequestCoordinator.run("academy", () -> {
                    completed.add("power-2");
                    return null;
                });
            });
            assertTrue(secondStarted.await(2, TimeUnit.SECONDS));
            Future<String> otherSite = workers.submit(
                    () -> PhoneRequestCoordinator.run("home", () -> "home-ready")
            );
            assertEquals("home-ready", otherSite.get(2, TimeUnit.SECONDS));
            assertThrows(TimeoutException.class, () -> second.get(100, TimeUnit.MILLISECONDS));
            releaseFirst.countDown();
            first.get(2, TimeUnit.SECONDS);
            second.get(2, TimeUnit.SECONDS);
            assertEquals(List.of("unlock-1", "power-2"), completed);
        } finally {
            releaseFirst.countDown();
            workers.shutdownNow();
        }
    }
}
