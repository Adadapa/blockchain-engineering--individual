# blockchain-engineering--individual

## Proof of Work

Copy the config template first:

```bash
cp lab1_config.json lab1_config.json
```

Then edit `lab1_config.json` with your real values. Both scripts read it by default.

The PoW miner is implemented in [lab1_pow.py](/Users/adaturgut/blockchain-engineering--individual/lab1_pow.py:1).

Run it with the current dummy values:

```bash
python3 lab1_pow.py
```

Override the exact bytes that will be hashed and later submitted:

```bash
python3 lab1_pow.py \
  --email your.name@student.tudelft.nl \
  --github-url https://github.com/your-user/your-repo
```

You can also just rely on `lab1_config.json`:

```bash
python3 lab1_pow.py
```

Important:

- The hash input is exactly `email_utf8 + b"\\n" + github_url_utf8 + b"\\n" + nonce_as_8_byte_big_endian`.
- The nonce is hashed as 8 binary bytes in big-endian order, not as decimal text.
- Changing the email or URL after mining invalidates the nonce.

## Community Discovery

The IPv8 community discovery client is implemented in [lab1_ipv8_client.py](/Users/adaturgut/blockchain-engineering--individual/lab1_ipv8_client.py:1).

Run it with a persistent key file:

```bash
python3 lab1_ipv8_client.py --key-file lab1_identity.pem
```

Or let it read the key path from `lab1_config.json`:

```bash
python3 lab1_ipv8_client.py
```

Important:

- The client joins only the lab community ID from the assignment.
- It does not trust every discovered peer in that community.
- It filters discovered peers by the exact server public key before treating a peer as the server.
- Keep the generated `.pem` file if you intend to reuse the same identity later.

To send a submission and receive the server response:

```bash
python3 lab1_ipv8_client.py \
  --submit \
  --nonce 123456789
```

If `email`, `github_url`, `key_file`, or `nonce` are present in `lab1_config.json`, the scripts use them automatically. CLI flags override the config file.

Important:

- The response handler is registered for `message_id = 2`.
- The submission is sent with IPv8 authenticated messaging via `ez_send`.
- The client ignores response packets from peers whose public key does not match the server.
