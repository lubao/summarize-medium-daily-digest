# Medium Cookies Configuration

This document explains the Medium cookie configuration used by the Medium Digest Summarizer system.

## Cookie Format

The system uses a JSON array format for storing Medium authentication cookies. Each cookie object contains the following properties:

### Cookie Object Structure

```json
{
    "domain": "string",           // Cookie domain (e.g., ".medium.com", "medium.com")
    "expirationDate": number,     // Unix timestamp for expiration (optional for session cookies)
    "hostOnly": boolean,          // Whether cookie is host-only
    "httpOnly": boolean,          // Whether cookie is HTTP-only (not accessible via JavaScript)
    "name": "string",            // Cookie name
    "path": "string",            // Cookie path (usually "/")
    "sameSite": "string",        // SameSite policy ("no_restriction", "lax", "strict")
    "secure": boolean,           // Whether cookie requires HTTPS
    "session": boolean,          // Whether cookie is a session cookie
    "storeId": null,            // Store ID (usually null)
    "value": "string"           // Cookie value
}
```

## Important Cookies for Medium Authentication

### Essential Authentication Cookies

1. **`uid`** - User ID cookie
   - Required for user identification
   - Domain: `.medium.com`
   - HttpOnly: `true`
   - Secure: `true`

2. **`sid`** - Session ID cookie
   - Required for session management
   - Domain: `.medium.com`
   - HttpOnly: `true`
   - Secure: `true`

3. **`xsrf`** - CSRF protection token
   - Required for CSRF protection
   - Domain: `medium.com`
   - HttpOnly: `true`
   - Secure: `true`

### Additional Cookies

4. **`_cfuvid`** - Cloudflare unique visitor ID
   - Used for bot protection
   - Session cookie
   - Domain: `.medium.com`

5. **`cf_clearance`** - Cloudflare clearance token
   - Required for bypassing Cloudflare protection
   - Domain: `.medium.com`
   - Critical for automated access

6. **`nonce`** - Security nonce
   - Additional security token
   - Domain: `.medium.com`

7. **Analytics Cookies** (`_ga`, `_gcl_au`, `_ga_7JY7T788PK`)
   - Google Analytics cookies
   - Not critical for authentication but may be expected

## File Location

The cookie configuration is stored in:
- **Local file**: `medium-cookie.json`
- **AWS Secrets Manager**: `medium-cookies` secret
- **CDK Configuration**: `medium_digest_summarizer_stack.py`

## Usage in the System

### 1. Secrets Manager Storage

The cookies are stored in AWS Secrets Manager as a JSON string:

```json
{
  "cookies": "[{cookie_object_1}, {cookie_object_2}, ...]"
}
```

### 2. Lambda Function Usage

The `fetch_articles` Lambda function:
1. Retrieves cookies from Secrets Manager using `get_medium_cookies()`
2. Converts JSON array to HTTP request format using `format_cookies_for_requests()`
3. Uses cookies in HTTP requests to Medium

### 3. Backward Compatibility

The system supports both:
- **New format**: JSON array of cookie objects (current)
- **Legacy format**: Simple cookie string (e.g., "name1=value1; name2=value2")

## Updating Cookies

### Method 1: Update CDK Stack

1. Modify `medium-cookie.json`
2. Update `medium_digest_summarizer_stack.py`
3. Deploy with `cdk deploy --profile medium-digest`

### Method 2: Direct AWS Console

1. Go to AWS Secrets Manager
2. Find the `medium-cookies` secret
3. Update the `cookies` value with new JSON array

### Method 3: AWS CLI

```bash
aws secretsmanager update-secret \
  --secret-id medium-cookies \
  --secret-string '{"cookies":"[{...new_cookie_array...}]"}' \
  --profile medium-digest \
  --region us-east-1
```

## Cookie Expiration

Monitor cookie expiration dates:
- Most cookies expire around **2025-01-12** to **2025-01-13**
- Session cookies (`_cfuvid`) expire when browser session ends
- Update cookies before expiration to maintain system functionality

## Security Considerations

1. **Never commit real cookies to version control**
2. **Use AWS Secrets Manager for production cookies**
3. **Rotate cookies regularly**
4. **Monitor for authentication failures**
5. **Use secure, httpOnly cookies when possible**

## Testing

The system includes comprehensive tests for cookie handling:
- `tests/test_secrets_manager.py` - Cookie parsing and formatting
- `tests/test_fetch_articles_integration.py` - End-to-end cookie usage
- `tests/test_fetch_articles_simple.py` - JSON format validation

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Check cookie expiration dates
   - Verify all essential cookies are present
   - Ensure cookie values are current

2. **Cloudflare Blocks**
   - Update `cf_clearance` token
   - Verify `_cfuvid` is present
   - Check if IP is blocked

3. **Format Errors**
   - Validate JSON syntax
   - Ensure all required fields are present
   - Check data types match schema

### Debug Commands

```bash
# Test cookie retrieval locally
python -c "from shared.secrets_manager import get_medium_cookies; print(get_medium_cookies())"

# Validate JSON format
python -c "import json; print(json.loads(open('medium-cookie.json').read()))"
```