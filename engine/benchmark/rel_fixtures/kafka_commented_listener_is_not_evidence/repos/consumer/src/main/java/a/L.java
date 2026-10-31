package a;
import org.springframework.kafka.annotation.KafkaListener;
/**
 * @KafkaListener(topics = "orders.created")
 */
public class L {
  // @KafkaListener(topics = "orders.created")
  void on(String m){}
}
