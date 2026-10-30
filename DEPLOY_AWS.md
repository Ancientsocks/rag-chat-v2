# Deploy Reading Room to AWS EC2 with hosted Gemini

This setup runs the FastAPI application, frontend, PDF uploads and persistent ChromaDB on one EC2 instance. Gemini performs LLM inference over HTTPS, so EC2 does not need to run Ollama or download Llama 3.

## Cost and security warnings

- AWS is not guaranteed to be permanently free. New-account credits and Free Tier eligibility depend on account age, region, instance type and current AWS offer. Review AWS Billing before creating resources.
- ChromaDB's default embedding function downloads an embedding model on first use. Allow extra disk, memory and startup time.
- A 1 GiB EC2 instance may run out of memory during installation, embedding initialization or PDF indexing. Select an instance with sufficient memory and check its price; a larger instance may incur charges.
- This application currently has no authentication or per-user document isolation. Restrict initial access to your own IP. Do not expose sensitive documents publicly until authentication and authorization are implemented.
- Keep the Gemini API key only in the EC2 .env file. Never commit it or place it in frontend code.
- Back up the reading_room_data Docker volume. Deleting it deletes uploaded PDFs and the ChromaDB index.

## 1. Create AWS and Gemini accounts

1. Create an AWS account at https://aws.amazon.com/free/ and review the Free account plan and credits offered to your account.
2. Enable MFA on the root account. Do not use root for routine server access.
3. Review AWS Budgets and billing alerts.
4. Create a Gemini API key at https://aistudio.google.com/app/apikey. Check current free-tier availability, regional eligibility and rate limits.
5. Confirm that gemini-2.5-flash is available to your API key. Change DEFAULT_MODEL and AVAILABLE_MODELS if required.

## 2. Launch EC2

1. Open the EC2 console and choose a region near your users.
2. Launch an Ubuntu Server LTS instance.
3. Choose an instance size with enough RAM for Python, ChromaDB and the embedding model. Do not assume a 1 GiB micro instance is sufficient. Check current Free Tier eligibility and estimated cost.
4. Create an SSH key pair and store the private key safely.
5. Security group: allow SSH TCP 22 from My IP only. For initial tests, allow TCP 8000 from My IP only. Do not open port 8000 to the whole internet.
6. Ensure the EBS disk has enough space for Docker images, dependencies, embedding model, PDFs and ChromaDB.
7. Review expected charges before launching.

## 3. Install Docker on Ubuntu

Connect using the SSH command shown in the EC2 console, then run:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and reconnect so Docker group membership applies.

## 4. Clone and configure

```bash
git clone https://github.com/Ancientsocks/rag-chat-v2.git
cd rag-chat-v2
cp .env.aws.example .env
nano .env
```

Replace the placeholder GEMINI_API_KEY with your real key. Save the file. Never commit .env.

## 5. Start the app

```bash
docker compose --env-file .env -f docker-compose.aws.yml up --build -d
docker compose --env-file .env -f docker-compose.aws.yml ps
docker compose --env-file .env -f docker-compose.aws.yml logs -f backend
curl http://localhost:8000/health
```

Expected health response contains status ok and vector_store chroma.

## 6. Initial test

With TCP 8000 allowed only from your IP, open http://EC2_PUBLIC_IP:8000 and http://EC2_PUBLIC_IP:8000/docs.

For a proper public deployment, configure a domain and HTTPS reverse proxy (for example Caddy) and implement authentication before allowing general internet access.

## 7. Updates and operations

```bash
docker compose --env-file .env -f docker-compose.aws.yml logs --tail=100 backend
docker compose --env-file .env -f docker-compose.aws.yml restart backend
git pull
docker compose --env-file .env -f docker-compose.aws.yml up --build -d
docker volume ls
```

Do not run docker compose down -v unless you intentionally want to delete the persistent documents and ChromaDB volume.

## Architecture

- FastAPI serves frontend and API on port 8000.
- ChromaDB persists under /app/data/chroma_db.
- Uploaded PDFs persist under /app/data/uploads.
- Gemini API performs generation; no Ollama container or local LLM weights are required.
- Authentication, per-user authorization, backups, quotas and monitoring are still required before production use.