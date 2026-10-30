# Deploy Reading Room to AWS EC2 with hosted Gemini

This setup runs the FastAPI application, PDF uploads and persistent ChromaDB on one EC2 instance. Gemini performs LLM inference over HTTPS, so EC2 does not need to run Ollama or download local LLM weights.

## Deployment status

The application has been deployed and smoke-tested on an Ubuntu 24.04 EC2 instance using Docker Compose, ChromaDB persistent storage and the hosted Gemini API. The deployment used `gemini-3.6-flash` after testing showed that the initially configured model returned HTTP 404 and another model temporarily returned HTTP 503. Model availability and routing can change; test the model with your own API key before relying on it.

## Cost and security warnings

- AWS is not guaranteed to be permanently free. New-account credits and Free Plan eligibility depend on account, region, instance type and current AWS offer. Review AWS Billing and credits regularly.
- ChromaDB's default embedding function downloads an embedding model on first use. Allow extra disk, memory and startup time.
- A 1 GiB EC2 instance may run out of memory during installation, embedding initialization or PDF indexing. Check instance pricing before choosing a larger instance.
- This application currently has no authentication or per-user document isolation. Restrict access to trusted IP addresses. Do not expose sensitive documents publicly until authentication and authorization are implemented.
- Keep the Gemini API key only in the EC2 `.env` file. Never commit it or place it in frontend code.
- Back up the `reading_room_data` Docker volume. Deleting it deletes uploaded PDFs and the ChromaDB index.

## 1. Create AWS and Gemini accounts

1. Create an AWS account at https://aws.amazon.com/free/ and review the plan and credits offered to your account.
2. Enable MFA on the root account. Do not use root for routine server access.
3. Review AWS Budgets and billing alerts.
4. Create a Gemini API key at https://aistudio.google.com/app/apikey. Check current model availability, regional eligibility and rate limits.

## 2. Launch EC2

1. Open the EC2 console and choose a region available to your account.
2. Launch an Ubuntu Server LTS instance.
3. Choose an instance size with enough RAM for Python, ChromaDB and the embedding model. Do not assume a 1 GiB micro instance is sufficient. Check current eligibility and estimated cost.
4. Create an SSH key pair and store the private key safely.
5. Security group: allow SSH TCP 22 from My IP only. For initial tests, allow TCP 8000 from My IP only. Do not open port 8000 to the whole internet.
6. Ensure the EBS disk has enough space for Docker images, dependencies, embedding model, PDFs and ChromaDB.
7. Review expected charges before launching.

## 3. Install Docker

On Ubuntu, install Docker Engine and the Compose plugin using the official Docker instructions: https://docs.docker.com/engine/install/ubuntu/

## 4. Clone and configure

Use the deployment branch or a merged commit containing `docker-compose.aws.yml`:

```bash
git clone --branch deploy/aws-hosted-llm --single-branch https://github.com/Ancientsocks/rag-chat-v2.git
cd rag-chat-v2
cp .env.aws.example .env
chmod 600 .env
nano .env
```

Set `GEMINI_API_KEY` to your real key. The example defaults to `gemini-3.6-flash`; verify that model is available to your key. Never commit `.env`.

## 5. Start the app

```bash
docker compose --env-file .env -f docker-compose.aws.yml config --quiet
docker compose --env-file .env -f docker-compose.aws.yml up --build -d
docker compose --env-file .env -f docker-compose.aws.yml ps
docker compose --env-file .env -f docker-compose.aws.yml logs --tail=100 backend
curl -i http://localhost:8000/health
```

## 6. Initial test

With TCP 8000 allowed only from your IP, open `http://EC2_PUBLIC_IP:8000` and `http://EC2_PUBLIC_IP:8000/docs`.

For a public deployment, configure a domain and HTTPS reverse proxy and implement authentication before allowing general internet access.

## 7. Updates and operations

```bash
docker compose --env-file .env -f docker-compose.aws.yml logs --tail=100 backend
docker compose --env-file .env -f docker-compose.aws.yml restart backend
git pull
docker compose --env-file .env -f docker-compose.aws.yml up --build -d
docker volume ls
```

Do not run `docker compose down -v` unless you intentionally want to delete the persistent documents and ChromaDB volume.

## Architecture

- FastAPI serves the frontend and API on port 8000.
- ChromaDB persists under `/app/data/chroma_db`.
- Uploaded PDFs persist under `/app/data/uploads`.
- Gemini API performs generation; no Ollama container or local LLM weights are required.
- Authentication, per-user authorization, backups, quotas, HTTPS and monitoring are still required before production use.
