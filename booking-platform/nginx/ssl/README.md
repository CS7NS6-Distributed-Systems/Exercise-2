# SSL Certificates for Nginx Load Balancer

## IMPORTANT: Certificate Files Required

This directory MUST contain the following SSL certificate files for HTTPS support:
- `nginx.crt` - SSL certificate file
- `nginx.key` - SSL private key file

**⚠️ DO NOT start the application without completing the SSL certificate setup below ⚠️**

## Quick Setup (Development)

```bash
# Navigate to this directory
cd /path/to/booking-platform/nginx/ssl

# Generate self-signed certificate (one-line command)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx.key -out nginx.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# Set proper permissions
chmod 644 nginx.crt
chmod 600 nginx.key

# Restart Nginx if it's already running
docker-compose restart nginx
```

## Detailed Certificate Generation Procedures

### Method 1: Basic One-Line Command (for Development)
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx.key -out nginx.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

### Method 2: Interactive Approach (More Control)
For more control over the certificate details:

1. Generate a private key:
```bash
openssl genrsa -out nginx.key 2048
```

2. Create a Certificate Signing Request (CSR):
```bash
openssl req -new -key nginx.key -out nginx.csr
```
   - You'll be prompted for information like Country, State, Organization, etc.
   - For "Common Name (CN)", enter your domain or `localhost` for local development

3. Generate a self-signed certificate:
```bash
openssl x509 -req -days 365 -in nginx.csr -signkey nginx.key -out nginx.crt
```

4. Verify your certificate:
```bash
openssl x509 -in nginx.crt -text -noout
```

### Method 3: With Subject Alternative Names (Multi-domain Support)

For certificates that need to support multiple domains:

1. Create a configuration file named `openssl.cnf`:
```bash
cat > openssl.cnf << EOL
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = US
ST = State
L = City
O = Organization
OU = Department
CN = localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = example.com
DNS.3 = www.example.com
IP.1 = 127.0.0.1
EOL
```

2. Generate the certificate:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx.key -out nginx.crt \
  -config openssl.cnf -extensions v3_req
```

## Installation and Configuration

1. Place both files in this directory (`nginx/ssl/`):
```bash
cp nginx.crt nginx.key /path/to/booking-platform/nginx/ssl/
```

2. Set proper permissions:
```bash
chmod 644 nginx.crt
chmod 600 nginx.key
```

3. Verify the files are in place and have correct permissions:
```bash
ls -la
# Should show something like:
# -rw-r--r-- 1 user group 1234 date nginx.crt
# -rw------- 1 user group 1234 date nginx.key
```

4. Restart Nginx to apply changes:
```bash
# From the project root directory
docker-compose restart nginx

# To verify Nginx loaded the certificates correctly
docker-compose logs nginx | grep -i "ssl"
```

## For Production Environments

### Option 1: Using Let's Encrypt (Recommended for Production)

Let's Encrypt provides free, automated certificates with automatic renewal.

1. Install Certbot:
```bash
apt-get update
apt-get install certbot python3-certbot-nginx
```

2. Obtain a certificate:
```bash
certbot --nginx -d example.com -d www.example.com
```

3. Copy certificates to this directory:
```bash
cp /etc/letsencrypt/live/example.com/fullchain.pem nginx.crt
cp /etc/letsencrypt/live/example.com/privkey.pem nginx.key
```

4. Set up automatic renewal:
```bash
# Test the renewal process
certbot renew --dry-run

# Add to crontab (runs twice daily)
echo "0 0,12 * * * root python -c 'import random; import time; time.sleep(random.random() * 3600)' && certbot renew -q" | sudo tee -a /etc/crontab > /dev/null
```

### Option 2: Using a Commercial Certificate

1. Purchase a certificate from a trusted CA (DigiCert, Comodo, etc.)
2. Generate a CSR (Certificate Signing Request):
```bash
openssl req -new -newkey rsa:2048 -nodes -keyout nginx.key -out request.csr
```
3. Submit the CSR to your certificate provider
4. Download the certificate files provided by the CA
5. Place the certificate and private key in this directory:
```bash
cp your_certificate.crt nginx.crt
cp your_private.key nginx.key
```
6. If you received intermediate certificates, concatenate them with your certificate:
```bash
cat your_certificate.crt intermediate_cert.crt root_cert.crt > nginx.crt
```

## Troubleshooting

### Certificate Issues

- Verify certificate validity:
```bash
openssl verify -CAfile /path/to/ca/chain.pem nginx.crt
```

- Check certificate expiration:
```bash
openssl x509 -enddate -noout -in nginx.crt
```

- Check certificate details:
```bash
openssl x509 -text -noout -in nginx.crt
```

### Common Errors

- **Certificate not trusted by browser**: 
  - For development, add an exception in your browser
  - For production, ensure you've included all intermediate certificates

- **Private key mismatch**: Verify key matches certificate:
```bash
openssl x509 -noout -modulus -in nginx.crt | openssl md5
openssl rsa -noout -modulus -in nginx.key | openssl md5
```
(Both commands should output the same MD5 hash)

- **Nginx fails to start**:
  - Check logs: `docker-compose logs nginx`
  - Verify file permissions: `ls -la nginx.key` (should be 600)
  - Ensure correct paths in nginx configuration

- **Certificate chain issues**:
  - Verify complete chain: `openssl verify -verbose -CAfile chain.pem nginx.crt`
  - Check chain order: Root CA → Intermediate CA(s) → Your certificate

## Security Best Practices

- ⚠️ **NEVER commit SSL certificate files to version control**
- Keep your private key secure and restrict access
- Regularly rotate certificates (typically every 1-2 years)
- Use at least 2048-bit RSA keys (4096-bit recommended for production)
- Use strong cipher suites in your Nginx configuration
- Always verify that private keys are protected from unauthorized access:
```bash
ls -la nginx.key  # Should show permissions like: -rw------- (600)
```
- Regularly audit who has access to the certificate files
- Add `*.crt` and `*.key` to your `.gitignore` file
- For production, consider using a certificate manager or secrets vault
- Set up monitoring for certificate expiration

## Validation and Testing

After setting up your certificates, validate your SSL configuration:

1. Test using OpenSSL:
```bash
openssl s_client -connect your-domain.com:443 -tls1_2
```

2. Online validators:
   - [SSL Labs Server Test](https://www.ssllabs.com/ssltest/)
   - [DigiCert SSL Checker](https://www.digicert.com/help/)

3. Test in multiple browsers to ensure compatibility 