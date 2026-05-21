# Runbooks

## Deploy Checklist

Use this after each production deploy.

1. Confirm Render deploy succeeded.
2. Open `/api/health`.
3. Open `/api/readiness`.
4. Confirm:
   - database backend is `postgres`
   - storage backend is `s3`
   - email is configured when SMTP is expected
5. Sign in with a test account.
6. Upload, download, and delete a small evidence file.
7. Generate a packet.
8. Open the export view.
9. Send a test email.
10. Check Render logs for `request.error` events.

## User Reports An Error

1. Ask the user for the request ID shown in the error message.
2. Search Render logs for that request ID.
3. Inspect `request.error`.
4. Confirm whether the issue is user input, auth/session, database, storage, email, or a code bug.
5. If a code bug is confirmed, create a fix branch or patch, run tests, deploy, and ask the user to retry.

## Evidence Upload Fails

1. Check `/api/readiness`.
2. Confirm storage backend is `s3`.
3. Confirm `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_REGION`, and credentials are set in Render.
4. Check S3 bucket policy and IAM permissions.
5. Search Render logs for the request ID.
6. Confirm the uploaded file type and size are allowed.

## Email Delivery Fails

1. Check `/api/readiness`.
2. Confirm email is configured.
3. Confirm `SMTP_HOST` matches the SES region where identities are verified.
4. Confirm sender domain or sender email is verified in SES.
5. If SES is still in sandbox, confirm the recipient email is verified too.
6. Use **Send test email** from the app sidebar.
7. Search Render logs for the request ID if sending fails.

## Password Reset Support

1. Ask the user to request a new reset email.
2. Confirm they are checking the email address attached to their account.
3. Ask them to use the newest link only.
4. If the link is expired, have them request another.
5. Do not ask users for their password or reset token.

## Account Deletion Request

The current app has self-service account deletion. Before broad launch, move deletion requests into a reviewed privacy workflow.

For current beta testing:

1. Ask the user to sign in.
2. Use **Delete account**.
3. Type `DELETE` when prompted.
4. Confirm they are signed out and the account data is gone.
