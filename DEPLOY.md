# Deploying to Vercel

## Quick Steps

1. **Install Vercel CLI** (if not already installed):
   ```bash
   npm install -g vercel
   ```

2. **Login to Vercel**:
   ```bash
   vercel login
   ```

3. **Deploy**:
   ```bash
   vercel
   ```
   
   Follow the prompts:
   - Set up and deploy? **Yes**
   - Which scope? (Select your account)
   - Link to existing project? **No**
   - Project name? (Press enter for default or type a name)
   - Directory? (Press enter for current directory)

4. **Deploy to production**:
   ```bash
   vercel --prod
   ```

## Alternative: Deploy via GitHub

1. Push your code to GitHub (make sure `market_journal.csv` and `index.html` are committed)
2. Go to [vercel.com](https://vercel.com)
3. Click "New Project"
4. Import your GitHub repository
5. Vercel will auto-detect and deploy

## Important Files for Deployment

- ✅ `index.html` - The main webpage
- ✅ `market_journal.csv` - The CSV data file
- ✅ `vercel.json` - Vercel configuration
- ✅ `package.json` - Required for Vercel builds

## Updating the Data

When you update the Excel file and want to update the website:

1. Convert Excel to CSV:
   ```bash
   python3 -c "import pandas as pd; pd.read_excel('Market Journal Fall 2025.xlsx').to_csv('market_journal.csv', index=False)"
   ```

2. Commit and push the updated CSV:
   ```bash
   git add market_journal.csv
   git commit -m "Update market journal data"
   git push
   ```

3. Vercel will automatically redeploy!

