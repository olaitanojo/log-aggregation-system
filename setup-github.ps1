# GitHub Setup Script for SRE Portfolio
# This script will prepare your repositories and provide GitHub setup instructions

Write-Host "🚀 Setting up GitHub repositories for SRE Portfolio..." -ForegroundColor Green
Write-Host ""

# Repository configurations
$repositories = @(
    @{
        Name = "SRE-Portfolio"
        Path = "."
        Description = "Comprehensive Site Reliability Engineering portfolio with 6 production-ready projects demonstrating monitoring, incident response, infrastructure automation, and operational excellence."
        Topics = @("sre", "devops", "monitoring", "infrastructure", "automation", "incident-response", "portfolio")
        IsMain = $true
    },
    @{
        Name = "prometheus-monitoring-stack"  
        Path = "prometheus-monitoring-stack"
        Description = "Production-ready monitoring and alerting system with Prometheus, Grafana, and AlertManager. Includes SLA/SLO monitoring, custom dashboards, and automated remediation workflows."
        Topics = @("prometheus", "grafana", "monitoring", "alerting", "sla", "slo", "observability")
        IsMain = $false
    },
    @{
        Name = "terraform-aws-infrastructure"
        Path = "terraform-aws-infrastructure"  
        Description = "Infrastructure as Code with Terraform for AWS. Multi-environment setup with auto-scaling, security best practices, and cost optimization."
        Topics = @("terraform", "aws", "infrastructure-as-code", "auto-scaling", "security", "cloud")
        IsMain = $false
    },
    @{
        Name = "sre-cicd-pipeline"
        Path = "sre-cicd-pipeline"
        Description = "SRE-focused CI/CD pipeline with comprehensive testing, blue-green deployments, canary releases, and automated rollback mechanisms."
        Topics = @("cicd", "github-actions", "blue-green", "canary", "deployment", "testing", "sre")
        IsMain = $false
    },
    @{
        Name = "incident-response-toolkit"
        Path = "incident-response-toolkit"
        Description = "Complete incident management system with React dashboard, automated runbooks, and chaos engineering framework with safety controls."
        Topics = @("incident-response", "chaos-engineering", "runbooks", "react", "python", "kubernetes")
        IsMain = $false
    },
    @{
        Name = "log-aggregation-system"
        Path = "log-aggregation-system"
        Description = "Centralized logging with ELK stack, real-time analysis, ML-powered anomaly detection, and comprehensive log processing pipeline."
        Topics = @("elk-stack", "elasticsearch", "logstash", "kibana", "logging", "anomaly-detection")
        IsMain = $false
    },
    @{
        Name = "capacity-planning-system"
        Path = "capacity-planning-system"
        Description = "AI-powered capacity planning with machine learning forecasting, multi-cloud monitoring, and cost optimization recommendations."
        Topics = @("machine-learning", "forecasting", "capacity-planning", "cost-optimization", "prophet", "influxdb")
        IsMain = $false
    }
)

# Function to initialize git repository
function Initialize-GitRepo {
    param($RepoPath, $RepoName)
    
    Write-Host "📁 Initializing Git repository for $RepoName..." -ForegroundColor Yellow
    
    if ($RepoPath -eq ".") {
        $currentPath = Get-Location
    } else {
        if (-not (Test-Path $RepoPath)) {
            Write-Host "⚠️  Directory $RepoPath not found!" -ForegroundColor Red
            return $false
        }
        Push-Location $RepoPath
    }
    
    try {
        # Initialize git if not already done
        if (-not (Test-Path ".git")) {
            git init
            Write-Host "✅ Git repository initialized" -ForegroundColor Green
        }
        
        # Create .gitignore if it doesn't exist
        if (-not (Test-Path ".gitignore") -and $RepoPath -ne ".") {
            Copy-Item "../.gitignore" ".gitignore" -ErrorAction SilentlyContinue
        }
        
        # Add all files
        git add .
        
        # Check if there are changes to commit
        $status = git status --porcelain
        if ($status) {
            $commitMessage = if ($RepoName -eq "SRE-Portfolio") {
                "Initial commit: Complete SRE Portfolio with 6 production-ready projects"
            } else {
                "Initial commit: $($repositories | Where-Object { $_.Name -eq $RepoName } | Select-Object -ExpandProperty Description)"
            }
            
            git commit -m $commitMessage
            Write-Host "✅ Initial commit created" -ForegroundColor Green
        }
        
        # Set default branch to main
        git branch -M main
        
        return $true
    }
    catch {
        Write-Host "❌ Error setting up $RepoName`: $_" -ForegroundColor Red
        return $false
    }
    finally {
        if ($RepoPath -ne ".") {
            Pop-Location
        }
    }
}

# Initialize all repositories
Write-Host "🔧 Initializing Git repositories..." -ForegroundColor Cyan
Write-Host ""

$successfulRepos = @()
foreach ($repo in $repositories) {
    if (Initialize-GitRepo -RepoPath $repo.Path -RepoName $repo.Name) {
        $successfulRepos += $repo
    }
}

Write-Host ""
Write-Host "✅ Git repositories initialized successfully!" -ForegroundColor Green
Write-Host ""

# Create GitHub repository creation commands
Write-Host "🌟 Creating GitHub repositories..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 1: Manual GitHub Repository Creation" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Go to https://github.com/new and create the following repositories:" -ForegroundColor White
Write-Host ""

foreach ($repo in $successfulRepos) {
    Write-Host "Repository Name: $($repo.Name)" -ForegroundColor Green
    Write-Host "Description: $($repo.Description)" -ForegroundColor White
    Write-Host "Visibility: Public" -ForegroundColor White
    Write-Host "Topics: $($repo.Topics -join ', ')" -ForegroundColor Gray
    Write-Host ""
}

Write-Host ""
Write-Host "Option 2: GitHub CLI Commands (if you install GitHub CLI)" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "First install GitHub CLI: https://cli.github.com/" -ForegroundColor White
Write-Host "Then run these commands:" -ForegroundColor White
Write-Host ""

# Generate GitHub CLI commands
$ghCommands = @"
# Login to GitHub
gh auth login

"@

foreach ($repo in $successfulRepos) {
    $topicsStr = $repo.Topics -join ","
    $ghCommands += @"
# Create $($repo.Name) repository
gh repo create $($repo.Name) --public --description "$($repo.Description)"

"@
}

Write-Host $ghCommands -ForegroundColor Cyan

Write-Host ""
Write-Host "🔗 Setting up remote connections and pushing to GitHub..." -ForegroundColor Cyan
Write-Host ""

# Create push script for each repository
$pushScript = @"
# After creating repositories on GitHub, run these commands:

"@

foreach ($repo in $successfulRepos) {
    $pushScript += @"
# Setup $($repo.Name)
"@
    if ($repo.Path -ne ".") {
        $pushScript += @"
cd $($repo.Path)
"@
    }
    
    $pushScript += @"
git remote add origin https://github.com/yourusername/$($repo.Name).git
git push -u origin main
"@
    
    if ($repo.Path -ne ".") {
        $pushScript += @"
cd ..
"@
    }
    
    $pushScript += @"


"@
}

# Save push commands to file
$pushScript | Out-File -FilePath "push-to-github.sh" -Encoding UTF8

Write-Host "📝 Push commands saved to push-to-github.sh" -ForegroundColor Green
Write-Host ""
Write-Host "Push Commands:" -ForegroundColor Yellow
Write-Host "=============" -ForegroundColor Yellow
Write-Host $pushScript -ForegroundColor White

# Create repository README template
$portfolioReadme = @"
# 📋 Repository Setup Instructions

## 📁 Repository Structure
Your SRE Portfolio consists of the following repositories:

"@

foreach ($repo in $successfulRepos) {
    $portfolioReadme += @"
### [$($repo.Name)](https://github.com/yourusername/$($repo.Name))
$($repo.Description)
**Topics:** $($repo.Topics -join ', ')

"@
}

$portfolioReadme += @"

## 🚀 Quick Setup

1. **Create GitHub repositories** using one of the methods above
2. **Update remote URLs** in the push commands with your GitHub username
3. **Run the push commands** to upload all projects to GitHub
4. **Enable GitHub Pages** for documentation (optional)
5. **Set up repository topics** for better discoverability

## 🔧 Post-Setup Tasks

- [ ] Update repository descriptions and topics
- [ ] Enable GitHub Actions for CI/CD
- [ ] Set up branch protection rules
- [ ] Configure repository settings (Issues, Wiki, etc.)
- [ ] Add collaborators if working in a team
- [ ] Set up GitHub Pages for project documentation

## 📊 Portfolio Metrics

- **Total Repositories:** $($successfulRepos.Count)
- **Lines of Code:** 12,000+
- **Technologies:** Python, JavaScript, Go, Terraform, Docker, Kubernetes
- **Domains:** Monitoring, IaC, CI/CD, Incident Response, Logging, Capacity Planning

## 🎯 Next Steps

1. Push all repositories to GitHub
2. Update your resume/LinkedIn with repository links
3. Create a portfolio website linking to these projects
4. Set up automated deployments for demonstration environments
5. Write blog posts about your SRE implementations

---

**Your SRE Portfolio is ready to showcase your expertise!** 🏆
"@

$portfolioReadme | Out-File -FilePath "GITHUB_SETUP.md" -Encoding UTF8

Write-Host "📚 Setup instructions saved to GITHUB_SETUP.md" -ForegroundColor Green
Write-Host ""

# Final summary
Write-Host "🎉 GitHub Setup Complete!" -ForegroundColor Green
Write-Host "========================" -ForegroundColor Green
Write-Host ""
Write-Host "✅ $($successfulRepos.Count) repositories prepared" -ForegroundColor Green
Write-Host "✅ Git repositories initialized with proper commits" -ForegroundColor Green
Write-Host "✅ Push commands generated in push-to-github.sh" -ForegroundColor Green
Write-Host "✅ Setup instructions saved in GITHUB_SETUP.md" -ForegroundColor Green
Write-Host ""
Write-Host "🔗 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Create repositories on GitHub (manually or with GitHub CLI)" -ForegroundColor White
Write-Host "2. Update 'yourusername' in push-to-github.sh with your GitHub username" -ForegroundColor White
Write-Host "3. Run the push commands to upload your portfolio" -ForegroundColor White
Write-Host ""
Write-Host "🏆 Your SRE Portfolio is ready for GitHub!" -ForegroundColor Green
