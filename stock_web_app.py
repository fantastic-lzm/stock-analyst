from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import fitz  # PyMuPDF
from werkzeug.utils import secure_filename
import requests  # For OpenRouter API calls

TARGET_INDICATORS = [
    "归母净利润", "归母净利润同比", "盈利预测", "营业总收入", "营业总收入同比", 
    "经营活动现金净流量", "投资活动现金净流量", "筹资活动现金净流量", 
    "ROE", "ROA", "销售毛利率", "销售净利率", 
    "销售费用/营业总收入", "管理费用/营业总收入", "研发费用/营业总收入", "财务费用/营业总收入",
    "应收账款/总资产", "存货/总资产", "在建工程/总资产", 
    "净资产", "负债/总资产", "重大股东变化", 
    "PE", "PB", "主营构成"
]

app = Flask(__name__, static_url_path='', static_folder='.')
CORS(app)  # Enable CORS for all routes
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.config['OPENROUTER_API_KEY'] = "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"  # Set your OpenRouter API key here

# Ensure uploads directory exists and is accessible
os.makedirs('uploads', exist_ok=True)

# Load stock data from multiple JSON files
def load_stock_data(page=1, per_page=20):
    data = []
    for i in range(1, 4):
        try:
            with open(f'stockData-{i}.json', 'r') as f:
                file_data = json.load(f)
                # Flatten the hierarchical data
                for industry, subcategories in file_data.items():
                    for subcategory, companies in subcategories.items():
                        data.extend(companies)
        except FileNotFoundError:
            continue
    
    total = len(data)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_data = data[start:end]
    
    return {
        'data': paginated_data,
        'total': total,
        'page': page,
        'per_page': per_page
    }

# Analyze company reports using AI
def analyze_company_reports(company_name, reports):
    try:
        # Prepare report summaries for analysis
        report_texts = []
        for year, url in reports.items():
            if url:  # Skip empty URLs
                report_texts.append(f"{year}年报链接: {url}")
        
        prompt = f"你是一位专业的财务分析专家，你精通从财报中提取关键财务数据，你需要精确定位并提取指定的财务指标，即使它们分散在文档的不同部分。"
        prompt += "请分析{company_name}的财务报告，包含以下年报:\n" + "\n".join(report_texts)
        prompt += "年报链接100%真实，请基于年报数据按以下指标进行分析：{TARGET_INDICATORS}"
        prompt += "\n\n请总结公司财务状况、发展趋势和潜在风险，并使用相关报表、趋势图等展示。用中文回答。"
        
        headers = {
            "Authorization": f"Bearer {app.config['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "anthropic/claude-3-sonnet",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"分析时出错: {str(e)}"

def download_pdf(url, company_name, year):
    """Download PDF from URL and save to organized folders"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Create company directory if not exists
        # Keep Chinese characters in directory name but remove special chars
        company_dir = ''.join(c for c in company_name if c.isalnum() or c in (' ', '_', '-'))
        company_dir = company_dir.strip().replace(' ', '_')
        save_dir = os.path.join(app.config['UPLOAD_FOLDER'], company_dir)
        os.makedirs(save_dir, exist_ok=True)
        
        # Generate standardized filename
        filename = f"{year}_report.pdf"
        safe_filename = secure_filename(filename)
        filepath = os.path.join(save_dir, safe_filename)
        
        # Save PDF file
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
                
        return filename  # Return just the filename without path
    except Exception as e:
        print(f"Failed to download PDF: {e}")
        return None

# Static files route
@app.route('/static/uploads/<path:filepath>')
def uploaded_file(filepath):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filepath)

# PDF preview endpoint
@app.route('/preview_pdf')
def preview_pdf():
    pdf_url = request.args.get('url')
    company_name = request.args.get('company')
    year = request.args.get('year')
    
    if not pdf_url or not company_name or not year:
        return jsonify({'error': 'Missing required parameters'}), 400
        
    # Check if file already exists
    company_dir = ''.join(c for c in company_name if c.isalnum() or c in (' ', '_', '-'))
    company_dir = company_dir.strip().replace(' ', '_')
    filename = f"{year}_report.pdf"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], company_dir, filename)
    
    if not os.path.exists(filepath):
        # File doesn't exist, download it
        filename = download_pdf(pdf_url, company_name, year)
        if not filename:
            return jsonify({'error': 'Failed to download PDF'}), 500
        
    # Return the static file URL with correct path separator
    return jsonify({
        'pdf_url': f'/static/uploads/{company_dir}/{filename}'
    })

# Main route
@app.route('/')
def index():
    return render_template('index.html')

# API endpoint for paginated data
@app.route('/api/stocks')
def get_stocks():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    data = load_stock_data(page, per_page)
    return jsonify(data)

# API endpoint for company analysis
@app.route('/api/analyze/<company_name>')
def analyze_company(company_name):
    # Create cache directory if not exists
    os.makedirs('analysis_cache', exist_ok=True)
    
    # Generate cache filename (replace special chars)
    cache_filename = ''.join(c for c in company_name if c.isalnum() or c in (' ', '_', '-'))
    cache_filename = cache_filename.strip().replace(' ', '_') + '.json'
    cache_path = os.path.join('analysis_cache', cache_filename)
    
    # Check cache first
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return jsonify(json.load(f))
    
    # Not in cache, perform analysis
    data = load_stock_data(1, 1000)  # Load all data to find the company
    for company in data['data']:
        if company['name'] == company_name:
            analysis = analyze_company_reports(company_name, company['reports'])
            result = {
                'company': company_name,
                'analysis': analysis,
                'reports': company['reports'],
                'cached': False
            }
            
            # Save to cache
            with open(cache_path, 'w') as f:
                json.dump(result, f)
            
            return jsonify(result)
    return jsonify({'error': 'Company not found'}), 404

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
