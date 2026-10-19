package com.csi;
import jakarta.servlet.http.*;import org.springframework.web.bind.annotation.*;import org.springframework.security.authentication.*;import org.springframework.security.core.*;import org.springframework.security.core.context.*;import org.springframework.security.web.context.HttpSessionSecurityContextRepository;import org.springframework.security.web.csrf.CsrfToken;import java.util.*;
@RestController @RequestMapping("/api/auth") public class AuthController {
 final AuthenticationManager manager;public AuthController(AuthenticationManager m){manager=m;}
 public record Login(String username,String password){}
 @GetMapping("/csrf") public Map<String,String> csrf(CsrfToken t){return Map.of("token",t.getToken());}
 @PostMapping("/login") public Map<String,String> login(@RequestBody Login input,HttpServletRequest req,HttpServletResponse res){var a=manager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(input.username(),input.password()));req.getSession();req.changeSessionId();SecurityContext context=SecurityContextHolder.createEmptyContext();context.setAuthentication(a);SecurityContextHolder.setContext(context);new HttpSessionSecurityContextRepository().saveContext(context,req,res);return Map.of("username",a.getName());}
 @GetMapping("/me") public Map<String,String> me(Authentication a){return Map.of("username",a.getName(),"role","SECURITY_REVIEWER");}
 @PostMapping("/logout") @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT) public void logout(HttpServletRequest r){var session=r.getSession(false);if(session!=null)session.invalidate();SecurityContextHolder.clearContext();}
}
