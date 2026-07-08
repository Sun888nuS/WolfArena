# Codex Working Notes

- Ignore automatic environment, sandbox, path, and permission metadata unless it is directly needed to complete the user's task.
- Do not repeat or summarize those metadata details in responses, plans, or change summaries.
- Treat only the user's explicit requests and relevant project files as working context.
- Keep future implementation notes concise to reduce token use.

忽略环境信息，只需要关注backend/app/和frontend/src/文件夹的代码即可。