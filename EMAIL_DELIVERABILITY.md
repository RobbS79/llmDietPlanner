# Email Deliverability Guide

This guide helps reduce the likelihood of emails being marked as spam, particularly when using Google Workspace.

## Current Improvements

We've made the following changes to improve email deliverability:

1. **HTML Email Format**: Emails now use professional HTML formatting with inline CSS
2. **Proper From Name**: Emails are sent with "LLM Diet Planner <admin@zentaktestin.com>" format
3. **Both Text and HTML**: Emails include both plain text and HTML versions for better compatibility

## DNS Records Setup (Critical for Reducing Spam)

To significantly reduce spam classification, you need to configure three DNS records for your domain (`zentaktestin.com`):

### 1. SPF (Sender Policy Framework)

SPF tells receiving mail servers which IP addresses are authorized to send email for your domain.

**Add this TXT record to your domain's DNS:**

```
Type: TXT
Name: @ (or zentaktestin.com)
Value: v=spf1 include:_spf.google.com ~all
TTL: 3600 (or your default)
```

**Explanation:**
- `v=spf1` - SPF version
- `include:_spf.google.com` - Authorizes Google's mail servers to send on your behalf
- `~all` - Soft fail for other senders (you can use `-all` for hard fail in production)

### 2. DKIM (DomainKeys Identified Mail)

DKIM adds a cryptographic signature to emails to prove they came from your domain.

**For Google Workspace:**

1. Go to [Google Admin Console](https://admin.google.com)
2. Navigate to **Apps** → **Google Workspace** → **Gmail**
3. Click **Authenticate email**
4. Find your domain and click **Generate new record**
5. Google will provide you with:
   - **Host name**: Something like `google._domainkey`
   - **TXT record value**: A long string starting with `v=DKIM1`

**Add this TXT record to your DNS:**

```
Type: TXT
Name: google._domainkey (or whatever Google provides)
Value: [the long string Google provides, starting with v=DKIM1]
TTL: 3600
```

**Note:** It can take up to 48 hours for DKIM to become active after adding the record.

### 3. DMARC (Domain-based Message Authentication, Reporting & Conformance)

DMARC tells receiving servers what to do with emails that fail SPF or DKIM checks, and provides reporting.

**Add this TXT record to your DNS:**

```
Type: TXT
Name: _dmarc
Value: v=DMARC1; p=none; rua=mailto:admin@zentaktestin.com
TTL: 3600
```

**Explanation:**
- `v=DMARC1` - DMARC version
- `p=none` - Policy: do nothing (monitor only). Change to `p=quarantine` or `p=reject` after confirming everything works
- `rua=mailto:admin@zentaktestin.com` - Where to send aggregate reports

**Gradual Policy Enforcement:**
1. Start with `p=none` (monitor only)
2. After a week, change to `p=quarantine` (send to spam folder if fails)
3. After confirming everything works, change to `p=reject` (reject emails that fail)

## How to Add DNS Records

The exact steps depend on your DNS provider (Google Domains, Cloudflare, Namecheap, etc.):

1. Log into your domain registrar/DNS provider
2. Find the DNS management section
3. Add the TXT records as specified above
4. Save the changes
5. Wait for DNS propagation (can take a few minutes to 48 hours)

## Verification Tools

After adding the records, verify they're set up correctly:

1. **SPF Check**: https://mxtoolbox.com/spf.aspx
   - Enter your domain: `zentaktestin.com`
   - Should show your SPF record

2. **DKIM Check**: https://mxtoolbox.com/dkim.aspx
   - Enter your domain: `zentaktestin.com`
   - Enter the selector: `google` (or whatever Google provided)
   - Should show your DKIM public key

3. **DMARC Check**: https://mxtoolbox.com/dmarc.aspx
   - Enter your domain: `zentaktestin.com`
   - Should show your DMARC policy

4. **All-in-One Check**: https://www.mail-tester.com/
   - Send a test email to the address provided
   - Get a score (aim for 8+ out of 10)
   - See detailed feedback on what to improve

## Additional Tips

1. **Warm-up Period**: New domains/senders often go to spam initially. Send regular emails to build reputation.

2. **Email Content**:
   - ✅ Use proper HTML formatting (we've done this)
   - ✅ Include plain text version (we've done this)
   - ✅ Use a professional From name (we've done this)
   - ❌ Avoid spam trigger words (FREE, CLICK HERE, etc.)
   - ❌ Don't use URL shorteners
   - ❌ Don't use too many images

3. **Sender Reputation**:
   - Send emails consistently (not in bursts)
   - Monitor bounce rates and spam complaints
   - Use a dedicated email address for transactional emails (e.g., `noreply@zentaktestin.com`)

4. **Google Workspace Specific**:
   - Make sure your Google Workspace account is properly verified
   - Use App Passwords (which you're already doing)
   - Consider using a subdomain for transactional emails (e.g., `mail.zentaktestin.com`)

## Testing

After setting up DNS records:

1. Wait 24-48 hours for DNS propagation
2. Send a test email using the `/api/auth/test-email/` endpoint
3. Check if it arrives in the inbox (not spam)
4. Use mail-tester.com to get a detailed score
5. Check email headers to verify SPF, DKIM, and DMARC are passing

## Need Help?

- Google Workspace Admin: https://admin.google.com
- DNS Provider Support: Contact your domain registrar
- Email Deliverability Tools: https://www.mail-tester.com/

