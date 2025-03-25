# SSL Certificates for Nginx Load Balancer

This directory should contain your SSL certificate files for HTTPS support:
- `nginx.crt` - SSL certificate file
- `nginx.key` - SSL private key file

## How to Generate Self-Signed SSL Certificates

For development/testing purposes, you can generate self-signed SSL certificates using OpenSSL:

### Method 1: Basic One-Line Command
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx.key -out nginx.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

### Method 2: Interactive Approach
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

## Installation Instructions

1. Place both files in this directory (`nginx/ssl/`):
```bash
cp nginx.crt nginx.key /path/to/booking-platform/nginx/ssl/
```

2. Set proper permissions:
```bash
chmod 644 nginx.crt
chmod 600 nginx.key
```

3. Restart Nginx to apply changes:
```bash
docker-compose restart nginx
```

## For Production Environments

### Option 1: Using Let's Encrypt (Recommended)
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

### Option 2: Using a Commercial Certificate
1. Purchase a certificate from a trusted CA (DigiCert, Comodo, etc.)
2. Follow their instructions to generate a CSR and obtain certificates
3. Place the certificate and private key in this directory
4. Update your Nginx configuration if required

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

### Common Errors
- **Certificate not trusted**: Ensure the CA is recognized or configure clients to trust your CA
- **Private key mismatch**: Verify key matches certificate:
```bash
openssl x509 -noout -modulus -in nginx.crt | openssl md5
openssl rsa -noout -modulus -in nginx.key | openssl md5
```
(Both commands should output the same MD5 hash)

## Security Best Practices

- ⚠️ **Never commit SSL certificate files to version control**
- Keep your private key secure and restrict access
- Regularly rotate certificates (typically every 1-2 years)
- Use at least 2048-bit RSA keys (4096-bit recommended for production)
- Always verify that private keys are protected from unauthorized access:
```bash
ls -la nginx.key  # Should show permissions like: -rw------- (600)
```
- Regularly audit who has access to the certificate files
- Add `*.crt` and `*.key` to your `.gitignore` file
- For production, consider using a certificate manager or secrets vault 