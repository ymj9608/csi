package com.csi;
import org.springframework.stereotype.Component;import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;import org.springframework.scheduling.annotation.Scheduled;import java.util.*;import java.util.concurrent.*;
@Component public class Events {
 record Listener(String scanId,SseEmitter emitter){}final List<Listener> listeners=new CopyOnWriteArrayList<>();
 public SseEmitter subscribe(String id){var emitter=new SseEmitter(25*60*1000L);var l=new Listener(id,emitter);listeners.add(l);emitter.onCompletion(()->listeners.remove(l));emitter.onTimeout(()->{listeners.remove(l);emitter.complete();});emitter.onError(e->listeners.remove(l));try{emitter.send(SseEmitter.event().name("update").data(Map.of("connected",true)));}catch(Exception e){listeners.remove(l);}return emitter;}
 public void publish(String id){if(org.springframework.transaction.support.TransactionSynchronizationManager.isSynchronizationActive()){org.springframework.transaction.support.TransactionSynchronizationManager.registerSynchronization(new org.springframework.transaction.support.TransactionSynchronization(){public void afterCommit(){send(id);}});}else send(id);}
 private void send(String id){for(var l:listeners)if(l.scanId()==null||l.scanId().equals(id))try{l.emitter().send(SseEmitter.event().name("update").data(Map.of("scanId",id)));}catch(Exception e){listeners.remove(l);l.emitter().complete();}}
 @Scheduled(fixedDelay=20000) public void heartbeat(){for(var l:listeners)try{l.emitter().send(SseEmitter.event().comment("heartbeat"));}catch(Exception e){listeners.remove(l);l.emitter().complete();}}
}
