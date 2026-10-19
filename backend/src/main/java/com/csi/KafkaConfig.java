package com.csi;
import org.springframework.context.annotation.*;import org.springframework.kafka.config.*;import org.springframework.kafka.core.*;import org.springframework.kafka.listener.*;import org.springframework.util.backoff.FixedBackOff;import org.apache.kafka.clients.admin.NewTopic;
@Configuration public class KafkaConfig {
 @Bean KafkaAdmin.NewTopics topics(){return new KafkaAdmin.NewTopics(topic("scan.request"),topic("scan.progress"),topic("scan.result"),topic("scan.log"),topic("scan.dlq"),topic("scan.progress.DLT"),topic("scan.result.DLT"),topic("scan.log.DLT"));}
 NewTopic topic(String n){return TopicBuilder.name(n).partitions(1).replicas(1).build();}
 @Bean ConcurrentKafkaListenerContainerFactory<String,String> kafkaListenerContainerFactory(ConsumerFactory<String,String> consumer,KafkaTemplate<String,String> template){var factory=new ConcurrentKafkaListenerContainerFactory<String,String>();factory.setConsumerFactory(consumer);factory.setCommonErrorHandler(new DefaultErrorHandler(new DeadLetterPublishingRecoverer(template),new FixedBackOff(1000,2)));return factory;}
}
