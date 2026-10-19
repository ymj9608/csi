package com.csi;
import org.springframework.boot.ApplicationRunner;import org.springframework.boot.ApplicationArguments;import org.springframework.stereotype.Component;import org.springframework.beans.factory.annotation.Value;import org.springframework.security.crypto.password.PasswordEncoder;import java.util.UUID;
@Component public class Bootstrap implements ApplicationRunner {
 final Db db;final PasswordEncoder encoder;final String username,password;
 public Bootstrap(Db db,PasswordEncoder encoder,@Value("${csi.admin-username}")String username,@Value("${csi.admin-password}")String password){this.db=db;this.encoder=encoder;this.username=username;this.password=password;}
 public void run(ApplicationArguments args){if(password.length()<12)throw new IllegalStateException("CSI_ADMIN_PASSWORD must be at least 12 characters");if(db.count("SELECT count(*) FROM users WHERE username=?",username)==0)db.jdbc.update("INSERT INTO users VALUES(?,?,?,?)",UUID.randomUUID(),username,encoder.encode(password),"SECURITY_REVIEWER");}
}
