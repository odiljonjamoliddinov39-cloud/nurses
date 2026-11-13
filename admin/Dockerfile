FROM node:20-alpine
WORKDIR /srv
COPY package.json ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev"]
