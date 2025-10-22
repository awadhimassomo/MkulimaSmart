from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from website.models import Category, Product
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the database with sample agricultural products'

    def handle(self, *args, **kwargs):
        self.stdout.write('Starting to seed products...')

        # Get or create a supplier user
        supplier, created = User.objects.get_or_create(
            email='marketplace@mkulimasmart.com',
            defaults={
                'first_name': 'Marketplace',
                'last_name': 'Admin',
                'is_supplier': True,
                'phone_number': '+255000000000'
            }
        )
        if created:
            supplier.set_password('admin123')
            supplier.save()
            self.stdout.write(self.style.SUCCESS(f'Created supplier user: {supplier.email}'))

        # Create Categories
        categories_data = [
            {'name': 'Seeds', 'slug': 'seeds', 'description': 'Quality seeds for various crops'},
            {'name': 'Fertilizers', 'slug': 'fertilizers', 'description': 'Organic and chemical fertilizers'},
            {'name': 'Crop Protection', 'slug': 'crop-protection', 'description': 'Pesticides and herbicides'},
            {'name': 'Animal Feed', 'slug': 'animal-feed', 'description': 'Feed for livestock and poultry'},
            {'name': 'Farm Machinery', 'slug': 'farm-machinery', 'description': 'Tractors and equipment'},
            {'name': 'Irrigation', 'slug': 'irrigation', 'description': 'Drip systems and sprinklers'},
            {'name': 'Fencing & Housing', 'slug': 'fencing', 'description': 'Farm infrastructure materials'},
            {'name': 'Farm Technology', 'slug': 'technology', 'description': 'Smart farming solutions'},
        ]

        categories = {}
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description']
                }
            )
            categories[cat_data['slug']] = category
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created category: {category.name}'))

        # Sample Products Data
        products_data = [
            # Seeds
            {
                'name': 'Hybrid Maize Seeds - SC627',
                'slug': 'hybrid-maize-seeds-sc627',
                'category': 'seeds',
                'description': 'High-yield hybrid maize seeds suitable for various climates. Resistant to drought and common pests. Maturity: 120-130 days.',
                'price': Decimal('45000.00'),
                'stock': 500,
            },
            {
                'name': 'Tomato Seeds - Roma VF',
                'slug': 'tomato-seeds-roma-vf',
                'category': 'seeds',
                'description': 'Determinate variety ideal for processing and fresh market. Disease resistant with excellent shelf life.',
                'price': Decimal('8500.00'),
                'stock': 200,
            },
            {
                'name': 'Sunflower Seeds - Hybrid',
                'slug': 'sunflower-seeds-hybrid',
                'category': 'seeds',
                'description': 'High oil content sunflower seeds for commercial production. Drought tolerant and disease resistant.',
                'price': Decimal('25000.00'),
                'stock': 150,
            },
            {
                'name': 'Rice Seeds - Supa',
                'slug': 'rice-seeds-supa',
                'category': 'seeds',
                'description': 'Premium quality rice seeds with high yield potential. Suitable for irrigated and rain-fed conditions.',
                'price': Decimal('35000.00'),
                'stock': 300,
            },
            
            # Fertilizers
            {
                'name': 'NPK 17-17-17 Fertilizer - 50kg',
                'slug': 'npk-17-17-17-50kg',
                'category': 'fertilizers',
                'description': 'Balanced NPK fertilizer suitable for all crops. Promotes healthy growth and maximum yield. 50kg bag.',
                'price': Decimal('85000.00'),
                'stock': 1000,
            },
            {
                'name': 'Urea Fertilizer - 50kg',
                'slug': 'urea-fertilizer-50kg',
                'category': 'fertilizers',
                'description': 'High nitrogen content (46%) for rapid vegetative growth. Ideal for maize, wheat, and vegetables.',
                'price': Decimal('75000.00'),
                'stock': 800,
            },
            {
                'name': 'Organic Compost Manure - 50kg',
                'slug': 'organic-compost-50kg',
                'category': 'fertilizers',
                'description': ' 100% organic compost from decomposed plant materials. Improves soil structure and fertility.',
                'price': Decimal('30000.00'),
                'stock': 500,
            },
            {
                'name': 'DAP Fertilizer - 50kg',
                'slug': 'dap-fertilizer-50kg',
                'category': 'fertilizers',
                'description': 'Di-Ammonium Phosphate (18-46-0) for strong root development. Best applied at planting.',
                'price': Decimal('95000.00'),
                'stock': 600,
            },
            
            # Crop Protection
            {
                'name': 'Glyphosate Herbicide - 1L',
                'slug': 'glyphosate-herbicide-1l',
                'category': 'crop-protection',
                'description': 'Broad-spectrum systemic herbicide for control of annual and perennial weeds. 480g/L concentration.',
                'price': Decimal('18000.00'),
                'stock': 250,
            },
            {
                'name': 'Cypermethrin Insecticide - 1L',
                'slug': 'cypermethrin-insecticide-1l',
                'category': 'crop-protection',
                'description': 'Effective against a wide range of pests including aphids, caterpillars, and beetles.',
                'price': Decimal('22000.00'),
                'stock': 180,
            },
            {
                'name': 'Fungicide - Mancozeb 80% WP',
                'slug': 'mancozeb-fungicide',
                'category': 'crop-protection',
                'description': 'Protectant fungicide for control of leaf spots, blights, and downy mildew on various crops.',
                'price': Decimal('15000.00'),
                'stock': 200,
            },
            
            # Animal Feed
            {
                'name': 'Dairy Cattle Feed - 70kg',
                'slug': 'dairy-cattle-feed-70kg',
                'category': 'animal-feed',
                'description': 'Complete feed for dairy cows. Contains essential nutrients for high milk production.',
                'price': Decimal('65000.00'),
                'stock': 400,
            },
            {
                'name': 'Poultry Layer Feed - 50kg',
                'slug': 'poultry-layer-feed-50kg',
                'category': 'animal-feed',
                'description': 'Balanced nutrition for laying hens. High calcium for strong eggshells.',
                'price': Decimal('55000.00'),
                'stock': 350,
            },
            {
                'name': 'Pig Grower Pellets - 50kg',
                'slug': 'pig-grower-pellets-50kg',
                'category': 'animal-feed',
                'description': 'Complete feed for growing pigs from 30kg to market weight. Promotes rapid growth.',
                'price': Decimal('58000.00'),
                'stock': 300,
            },
            
            # Farm Machinery
            {
                'name': 'Hand Tractor - 8HP Diesel',
                'slug': 'hand-tractor-8hp-diesel',
                'category': 'farm-machinery',
                'description': 'Compact walking tractor perfect for small to medium farms. Fuel efficient and easy to operate.',
                'price': Decimal('3500000.00'),
                'stock': 15,
            },
            {
                'name': 'Knapsack Sprayer - 20L',
                'slug': 'knapsack-sprayer-20l',
                'category': 'farm-machinery',
                'description': 'Manual backpack sprayer with adjustable nozzle. Ideal for pesticide and fertilizer application.',
                'price': Decimal('45000.00'),
                'stock': 100,
            },
            {
                'name': 'Maize Sheller Machine',
                'slug': 'maize-sheller-machine',
                'category': 'farm-machinery',
                'description': 'Electric maize shelling machine. Processes up to 500kg per hour with minimal grain damage.',
                'price': Decimal('850000.00'),
                'stock': 25,
            },
            
            # Irrigation
            {
                'name': 'Drip Irrigation Kit - 1 Acre',
                'slug': 'drip-irrigation-kit-1-acre',
                'category': 'irrigation',
                'description': 'Complete drip irrigation system for 1 acre. Includes pipes, emitters, filters, and fittings.',
                'price': Decimal('450000.00'),
                'stock': 50,
            },
            {
                'name': 'Sprinkler System - Rotating',
                'slug': 'sprinkler-system-rotating',
                'category': 'irrigation',
                'description': 'Heavy-duty rotating sprinkler with adjustable coverage. Covers up to 30m diameter.',
                'price': Decimal('85000.00'),
                'stock': 75,
            },
            {
                'name': 'Water Pump - 2HP Submersible',
                'slug': 'water-pump-2hp-submersible',
                'category': 'irrigation',
                'description': 'Submersible water pump for irrigation and domestic use. Maximum head: 50m, flow rate: 100L/min.',
                'price': Decimal('280000.00'),
                'stock': 40,
            },
            
            # Fencing & Housing
            {
                'name': 'Barbed Wire - 500m Roll',
                'slug': 'barbed-wire-500m',
                'category': 'fencing',
                'description': 'Galvanized barbed wire for farm fencing. Durable and weather resistant.',
                'price': Decimal('65000.00'),
                'stock': 120,
            },
            {
                'name': 'Chicken Coop Wire Mesh - 30m',
                'slug': 'chicken-wire-mesh-30m',
                'category': 'fencing',
                'description': 'Heavy gauge wire mesh for poultry housing. 1m height, rust resistant.',
                'price': Decimal('35000.00'),
                'stock': 80,
            },
            
            # Technology
            {
                'name': 'Soil pH Meter',
                'slug': 'soil-ph-meter',
                'category': 'technology',
                'description': 'Digital soil pH and moisture meter. Helps optimize soil conditions for better crop growth.',
                'price': Decimal('25000.00'),
                'stock': 50,
            },
            {
                'name': 'Weather Station - Portable',
                'slug': 'weather-station-portable',
                'category': 'technology',
                'description': 'Portable weather monitoring device. Measures temperature, humidity, rainfall, and wind speed.',
                'price': Decimal('120000.00'),
                'stock': 20,
            },
        ]

        # Create Products
        created_count = 0
        for product_data in products_data:
            category_slug = product_data.pop('category')
            category = categories[category_slug]
            
            product, created = Product.objects.get_or_create(
                slug=product_data['slug'],
                defaults={
                    **product_data,
                    'category': category,
                    'supplier': supplier,
                    'is_active': True,
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created product: {product.name}'))

        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully seeded {created_count} products!'))
        self.stdout.write(self.style.SUCCESS(f'📦 Total products in database: {Product.objects.count()}'))
        self.stdout.write(self.style.SUCCESS(f'🏷️  Total categories: {Category.objects.count()}'))
