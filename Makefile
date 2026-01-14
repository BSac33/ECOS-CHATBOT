.PHONY: help setup reset seed db-shell logs stop clean test

help:
	@echo "🎓 ECOS CHATBOT - Commandes disponibles"
	@echo ""
	@echo "  make setup    - Démarre tous les services (DB + API + migration)"
	@echo "  make seed     - Remplit la base avec des cas d'exemple (⚠️  services doivent être lancés)"
	@echo "  make reset    - Arrête tout, supprime la DB et redémarre avec seed"
	@echo "  make db-shell - Ouvre un shell PostgreSQL interactif"
	@echo "  make logs     - Affiche les logs en temps réel"
	@echo "  make stop     - Arrête tous les services"
	@echo "  make clean    - Arrête et supprime tous les conteneurs/volumes"
	@echo "  make test     - Lance un test complet du workflow CLI"
	@echo ""

setup:
	@echo "🚀 Démarrage des services Docker..."
	cd backend_ecos_chatbot && docker-compose up -d
	@echo "⏳ Attente que les services soient prêts..."
	@sleep 5
	@echo "✅ Services démarrés"
	@echo ""
	@echo "💡 Pour remplir la base avec des exemples :"
	@echo "   make seed"

seed:
	@echo "🌱 Remplissage de la base de données avec des cas d'exemple..."
	cd backend_ecos_chatbot && docker-compose exec fastapi python seed_database.py
	@echo ""
	@echo "✅ Base de données seedée avec succès!"
	@echo ""
	@echo "🎯 Pour tester :"
	@echo "   python ecos_cli.py case-list"
	@echo "   python ecos_cli.py chat-loop 1"

reset:
	@echo "🔄 Reset complet de l'environnement..."
	@echo "⏹️  Arrêt des services..."
	cd backend_ecos_chatbot && docker-compose down
	@echo "🗑️  Suppression des données..."
	rm -rf backend_ecos_chatbot/data/postgres
	@echo "🚀 Redémarrage des services..."
	cd backend_ecos_chatbot && docker-compose up -d
	@echo "⏳ Attente de la disponibilité des services (15s)..."
	@sleep 15
	@echo "🌱 Seed de la base de données..."
	cd backend_ecos_chatbot && docker-compose exec fastapi python seed_database.py
	@echo ""
	@echo "✅ Reset terminé avec succès!"
	@echo ""
	@echo "🎯 Environnement prêt pour les tests"

db-shell:
	@echo "🐘 Connexion à PostgreSQL..."
	cd backend_ecos_chatbot && docker-compose exec database psql -U ecos_chatbot -d ecos_chatbot_db

logs:
	@echo "📋 Logs en temps réel (Ctrl+C pour quitter)..."
	cd backend_ecos_chatbot && docker-compose logs -f

stop:
	@echo "⏹️  Arrêt des services..."
	cd backend_ecos_chatbot && docker-compose down
	@echo "✅ Services arrêtés"

clean:
	@echo "🧹 Nettoyage complet..."
	cd backend_ecos_chatbot && docker-compose down -v
	rm -rf backend_ecos_chatbot/data/postgres
	@echo "✅ Nettoyage terminé"

test:
	@echo "🧪 Test du workflow complet..."
	@echo ""
	@echo "1️⃣  Liste des cas disponibles:"
	python ecos_cli.py case-list
	@echo ""
	@echo "2️⃣  Pour tester un cas d'interrogatoire:"
	@echo "   python ecos_cli.py chat-loop 1"
	@echo ""
	@echo "3️⃣  Pour finaliser et évaluer:"
	@echo "   python ecos_cli.py attempt-finalize <attempt_id>"
	@echo "   python ecos_cli.py attempt-evaluate <attempt_id>"
	@echo ""
