package a;
import org.springframework.web.client.RestTemplate;
import org.springframework.beans.factory.annotation.Value;
public class C {
  @Value("${client.url}") String u;
  RestTemplate rt;
  void f(){
    rt.getForObject(u + "/api/items/1", String.class);
  }
}
