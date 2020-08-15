# utility-scripts

Miscellaneous useful scripts.

## **awslogin**

Use 1Password TOTPs (time-based one-time passwords) to authenticate accounts
with MFA enabled with the aws command-line tool.

When your AWS account has MFA enabled and you want to authenticate with the
aws client (so you can access AWS resources locally, for example) you need to
specify a second factor.  If your second factor is 1Password's
TOTP (time-based one-time passwords), this script will make authenticating
(a little) easier.
