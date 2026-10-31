package a;
import org.springframework.web.bind.annotation.*;
@RestController
public class K {
  @GetMapping("/api/items/{id}")
  public String get(@PathVariable String id){return "";}
}
