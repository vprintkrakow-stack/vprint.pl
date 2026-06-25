# Render PDF Color Check

## Files
- app.py
- requirements.txt
- render.yaml

## Deploy on Render
1. Create a new GitHub repository.
2. Upload these files.
3. In Render choose New + > Web Service.
4. Connect your GitHub repo.
5. Render should detect `render.yaml`.
6. Deploy.
7. After deploy, your endpoint will be:
   `https://YOUR-SERVICE.onrender.com/analyze-pdf`

## Test
Use curl:

```bash
curl -X POST https://pdf-color-check.onrender.com/analyze-pdf -F "file=@sample.pdf"
```