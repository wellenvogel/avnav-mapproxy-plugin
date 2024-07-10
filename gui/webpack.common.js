const path = require('path');
const CopyPlugin = require("copy-webpack-plugin");
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
  target: ['web','es5'],
  entry: path.resolve(__dirname,'./src/index.js'),
  output: {
    path: path.resolve(__dirname, 'build'),
    filename: 'bundle.js',
      hashFunction: "xxhash64"
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
              //exclude: /node_modules/,
              use: {
                  loader: 'babel-loader',
                  options: {
                    presets: [['@babel/preset-env',{
                        targets: {
                            browsers: "> 0.25%, not dead, safari 9, safari 10, safari 11"
                        }
                    }]],
                    plugins: [
                          ["prismjs", {
                              "languages": ["javascript", "css", "markup","yaml"    ],
                              "plugins": ["line-numbers"],

                          }]
                      ]

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
                  publicPath: 'lib',
                  name: '[sha256:hash].[ext]'
              }
          }
      ]
  },
  devServer: {
    port: 9000
  }
};
