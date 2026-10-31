package a;
import org.springframework.kafka.core.KafkaTemplate;
public class P {
  KafkaTemplate<String,String> kafkaTemplate;
  void f(){ kafkaTemplate.send("orders.created", "x"); }
}
