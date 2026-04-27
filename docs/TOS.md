# GitHub Copilot terms — read this before sharing

GitHub's terms for Copilot:

> "GitHub Copilot is licensed for use by you, the individual user. You may
> not share your Copilot subscription with others or use it for any
> automated bulk activity."

Re-exposing your Copilot via this proxy means *another person's traffic*
hits GitHub using *your* OAuth token. GitHub's abuse-detection systems can:

1. Issue a warning email to your account.
2. Temporarily revoke your Copilot access.
3. Permanently terminate your Copilot subscription.

## Mitigations baked into this project

- `copilot-api` is started with `--rate-limit 10 --wait` (≤ 1 req per 10 s).
- Each issued key can have a `--max-rpm` cap.
- All traffic is logged so you can spot abnormal usage.

## Recommendations

- Use this **only** for yourself, or for trusted personal use (e.g. a single
  friend, a personal app). Do not publish the key publicly.
- Keep aggregate volume low — GitHub mostly flags *patterns* (sudden spikes,
  parallel high-throughput, scraping).
- If you receive a warning email, stop the tunnel immediately and revoke
  all keys.

You assume all risk. The authors of this project are not responsible for
account suspensions.
