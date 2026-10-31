package a;
import org.springframework.kafka.annotation.KafkaListener;
public class L {
  @KafkaListener(topics = "orders.created", groupId = "g")
  void on(String m){}
}
