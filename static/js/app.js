// Load stock data
async function loadStockData(page = 1) {
    console.log(`Loading stock data for page ${page}...`);
    const response = await fetch(`/api/stocks?page=${page}`);
    const data = await response.json();
    
    // Render table
    const tbody = document.getElementById('stockData');
    tbody.innerHTML = data.data.map(item => `
        <tr>
            <td>${item.name || 'N/A'} (${item.code || 'N/A'})</td>
            <td>
                ${item.reports && typeof item.reports === 'object' ? 
                  Object.entries(item.reports).reverse().map(([year, url]) => `
                    <a href="#" class="pdf-link" data-pdf="${url}">${year}年报</a><br>
                  `).join('') : 'No reports'}
            </td>
            <td>
                <button class="btn btn-sm btn-primary analyze-btn" 
                        data-company="${item.name}"
                        data-code="${item.code}">
                    Analyze
                </button>
            </td>
        </tr>
    `).join('');
    
    // Render pagination
    const pagination = document.getElementById('pagination');
    const totalPages = Math.ceil(data.total / data.per_page);
    
    let paginationHTML = '';
    for (let i = 1; i <= totalPages; i++) {
        paginationHTML += `
            <li class="page-item ${i === page ? 'active' : ''}">
                <a class="page-link" href="#" data-page="${i}">${i}</a>
            </li>
        `;
    }
    pagination.innerHTML = paginationHTML;
    
    // Add event listeners
    document.querySelectorAll('.page-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            loadStockData(parseInt(e.target.dataset.page));
        });
    });
    
    // PDF preview handler
    document.querySelectorAll('.pdf-link').forEach(link => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            const pdfUrl = e.target.dataset.pdf;
            console.log('Loading PDF:', pdfUrl);
            
            const modal = new bootstrap.Modal(document.getElementById('pdfModal'));
            const iframe = document.getElementById('pdfViewer');
            const loadingDiv = document.getElementById('pdfLoading');
            
            // Show loading state
            iframe.src = '';
            loadingDiv.classList.add('pdf-loading-active');
            loadingDiv.classList.remove('pdf-loading-hidden');
            iframe.classList.add('pdf-loading-hidden');
            iframe.classList.remove('pdf-viewer-active');
            modal.show();
            
            try {
                // Get PDF URL from backend
                const company = e.target.closest('tr').querySelector('td:first-child').textContent.split('(')[0].trim();
                const year = e.target.textContent.match(/\d+/)[0];
                const response = await fetch(`/preview_pdf?url=${encodeURIComponent(pdfUrl)}&company=${encodeURIComponent(company)}&year=${year}`);
                const data = await response.json();
                
                // Set iframe source and hide loading
                iframe.src = data.pdf_url;
                loadingDiv.classList.remove('pdf-loading-active');
                loadingDiv.classList.add('pdf-loading-hidden');
                iframe.classList.remove('pdf-loading-hidden');
                iframe.classList.add('pdf-viewer-active');
                
            } catch (error) {
                console.error('PDF loading error:', error);
                document.getElementById('pageInfo').innerHTML = `
                    <div class="alert alert-danger">
                        Failed to load PDF: ${error.message}
                    </div>
                `;
            }
        });
    });
    
    document.querySelectorAll('.analyze-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const button = e.target;
            const company = button.dataset.company;
            const code = button.dataset.code;
            
            // Show loading state
            button.innerHTML = `
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Analyzing...
            `;
            button.disabled = true;
            
            try {
                // Show modal immediately with loading state
                const modal = new bootstrap.Modal(document.getElementById('analysisModal'));
                document.getElementById('analysisLoading').style.display = 'flex';
                document.getElementById('analysisContent').style.display = 'none';
                modal.show();
                
                const analysis = await analyzeCompany(company, code);
                
                // Format analysis text with proper line breaks and spacing
                const formattedAnalysis = analysis
                    .replace(/\n/g, '<br>')
                    .replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
                
                // Show analysis result
                document.getElementById('analysisLoading').style.display = 'none';
                document.getElementById('analysisContent').style.display = 'block';
                document.getElementById('analysisContent').innerHTML = `
                    <h4>${company} (${code}) Analysis</h4>
                    <div class="alert alert-info p-3" style="white-space: pre-wrap;">${formattedAnalysis}</div>
                `;
                
            } catch (error) {
                console.error('Analysis error:', error);
                document.getElementById('analysisLoading').style.display = 'none';
                document.getElementById('analysisContent').style.display = 'block';
                document.getElementById('analysisContent').innerHTML = `
                    <div class="alert alert-danger">
                        Error analyzing company: ${error.message}
                    </div>
                `;
            } finally {
                // Reset button state
                button.innerHTML = 'Analyze';
                button.disabled = false;
            }
        });
    });
}

// Analyze company data
async function analyzeCompany(company, code) {
    console.log(`Analyzing company: ${company}`);
    try {
        const response = await fetch(`/api/analyze/${encodeURIComponent(company)}`);
        const data = await response.json();
        return data.analysis;
    } catch (error) {
        console.error('Analysis error:', error);
        throw error;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStockData();
});
