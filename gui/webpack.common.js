const path = require('path');
const CopyPlugin = require("copy-webpack-plugin");
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
  entry: path.resolve(__dirname,'./src/index.js'),
  output: {
    path: path.resolve(__dirname, 'build'),
    filename: 'bundle.js'
  },
  plugins: [
    new CopyPlugin({
      patterns: [
            { from: path.resolve(__dirname,"static")},
            { from: path.resolve(__dirname,"lib")+"/codeflask*"}
      ],
    }),
    new MiniCssExtractPlugin({
      filename: 'main.css'
    })
  ],
  module:{
      rules:[
          {
              test: /\.js$|\.jsx$/,
              exclude: /node_modules/,
              use: {
                  loader: 'babel-loader',
                  options: {
                    presets: ['@babel/preset-env']
                  }
              }
          },
          {
            test: /\.css$|\.less$/,
            use:[MiniCssExtractPlugin.loader,'css-loader','less-loader']
          },
          {
              test: /\.(ttf|eot|svg|png|jpg|gif|ico)(\?v=[0-9]\.[0-9]\.[0-9])?$/,
              loader: 'file-loader',
              options:{
                  outputPath: 'lib',
                  publicPath: 'lib'
              }
          }
      ]
  },
  devServer: {
    port: 9000
  }
};
