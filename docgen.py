from docgen.api import create_app

app = create_app()

if __name__ == "__main__":
    print("DocGen Agent 启动中...")
    print("请在浏览器中打开: http://localhost:5000")
    app.run(debug=True, port=5000)
